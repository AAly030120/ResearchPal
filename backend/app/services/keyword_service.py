"""
Keyword extraction and similar paper recommendation service for ResearchPal.
Uses scikit-learn TF-IDF + jieba segmentation for Chinese text support,
and Crossref API for similar paper discovery.
"""

import re
import math
import asyncio
from typing import List, Dict, Optional
from collections import Counter

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Try to import aiohttp for async HTTP, fall back to requests
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

import urllib.request
import json


# ─── Text Preprocessing ────────────────────────────────────────────────

def _segment_text(text: str) -> List[str]:
    """Segment text into words, handling both Chinese and English."""
    # Detect if text contains Chinese characters
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
    
    if has_chinese:
        # Use jieba for Chinese segmentation
        words = jieba.lcut(text)
        # Filter: keep words > 1 char, remove pure punctuation/whitespace
        words = [w.strip() for w in words if len(w.strip()) > 1 and not re.match(r'^[\s\d\W_]+$', w)]
        return words
    else:
        # English: split by whitespace, remove punctuation, lowercase
        words = re.findall(r'[a-zA-Z]{2,}', text.lower())
        # Remove common stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'shall', 'can', 'need', 'dare',
            'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
            'we', 'us', 'our', 'you', 'your', 'he', 'she', 'his', 'her', 'not',
            'no', 'nor', 'so', 'as', 'if', 'then', 'than', 'too', 'very', 'just',
            'also', 'now', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
            'only', 'own', 'same', 'into', 'over', 'about', 'after', 'between',
            'through', 'during', 'before', 'while', 'which', 'who', 'whom',
        }
        return [w for w in words if w not in stopwords]


def _prepare_documents(text: str, segment: bool = True) -> List[str]:
    """Prepare text for TF-IDF by segmenting and joining words back."""
    if not text or not text.strip():
        return []
    
    # Split into paragraphs or sections for better keyword extraction
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 20]
    
    if not paragraphs:
        paragraphs = [text]
    
    if segment:
        documents = [' '.join(_segment_text(p)) for p in paragraphs]
    else:
        documents = paragraphs
    
    return documents


# ─── Keyword Extraction ────────────────────────────────────────────────

def extract_keywords(text: str, top_n: int = 15) -> List[Dict[str, float]]:
    """
    Extract keywords from text using TF-IDF.
    
    Args:
        text: Input text to analyze
        top_n: Number of top keywords to return (default 15)
    
    Returns:
        List of {keyword: score} dictionaries, sorted by relevance descending
    """
    if not text or not text.strip():
        return []
    
    documents = _prepare_documents(text, segment=True)
    if not documents or all(not d.strip() for d in documents):
        return []
    
    try:
        # Use TF-IDF with both unigrams and bigrams
        vectorizer = TfidfVectorizer(
            max_features=200,
            ngram_range=(1, 2),
            max_df=0.85,
            min_df=1,
            sublinear_tf=True,
        )
        
        tfidf_matrix = vectorizer.fit_transform(documents)
        
        # Get feature names and sum scores across all documents
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.sum(axis=0).A1  # Sum across all docs
        
        # Sort by score
        keyword_scores = sorted(
            zip(feature_names, scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Filter out very short or digit-only keywords
        # Also filter out proper nouns that look like author names
        filtered = []
        for kw, score in keyword_scores:
            clean_kw = kw.strip()
            if len(clean_kw) < 2:
                continue
            if re.match(r'^\d+$', clean_kw):
                continue
            # Skip likely proper nouns / author names (starts with uppercase in English, single words)
            if re.match(r'^[A-Z][a-z]+$', clean_kw) and len(clean_kw) <= 8:
                continue
            filtered.append({"keyword": clean_kw, "score": round(float(score), 4)})
            if len(filtered) >= top_n:
                break
        
        return filtered
    except Exception as e:
        # Fallback to simple word frequency for very short texts
        words = _segment_text(text)
        counter = Counter(words)
        total = sum(counter.values()) or 1
        return [
            {"keyword": w, "score": round(c / total, 4)}
            for w, c in counter.most_common(top_n)
            if len(w) >= 2
        ]


# ─── Similar Paper Recommendation ──────────────────────────────────────

CROSSREF_API = "https://api.crossref.org/works"


def _search_crossref_sync(query: str, rows: int = 5) -> List[Dict]:
    """Search Crossref API synchronously (fallback when aiohttp not available)."""
    params = {
        "query": query,
        "rows": rows,
        "sort": "relevance",
        "order": "desc",
    }
    query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{CROSSREF_API}?{query_string}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchPal/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        results = []
        items = data.get("message", {}).get("items", [])
        for item in items:
            # Extract title
            title = ""
            title_list = item.get("title", [])
            if title_list:
                title = title_list[0]
            
            # Extract authors
            authors = []
            for author in item.get("author", []):
                family = author.get("family", "")
                given = author.get("given", "")
                if family:
                    name = f"{given} {family}".strip() if given else family
                    authors.append(name)
            
            doi = item.get("DOI", "")
            
            # Publication year
            year = ""
            pub_parts = item.get("published-print", {}) or item.get("published-online", {})
            date_parts = pub_parts.get("date-parts", [[None]])
            if date_parts and date_parts[0] and date_parts[0][0]:
                year = str(date_parts[0][0])
            
            # Journal / container
            container = item.get("container-title", [""])[0] if item.get("container-title") else ""
            
            if title:
                results.append({
                    "title": title,
                    "authors": authors[:5],  # Max 5 authors
                    "doi": doi,
                    "year": year,
                    "journal": container,
                    "url": f"https://doi.org/{doi}" if doi else "",
                })
        
        return results
    except Exception:
        return []


async def _search_crossref_async(query: str, rows: int = 5) -> List[Dict]:
    """Search Crossref API asynchronously."""
    if not HAS_AIOHTTP:
        return _search_crossref_sync(query, rows)
    
    params = {
        "query": query,
        "rows": rows,
        "sort": "relevance",
        "order": "desc",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CROSSREF_API,
                params=params,
                headers={"User-Agent": "ResearchPal/1.0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []
    
    results = []
    items = data.get("message", {}).get("items", [])
    for item in items:
        title = ""
        title_list = item.get("title", [])
        if title_list:
            title = title_list[0]
        
        authors = []
        for author in item.get("author", []):
            family = author.get("family", "")
            given = author.get("given", "")
            if family:
                name = f"{given} {family}".strip() if given else family
                authors.append(name)
        
        doi = item.get("DOI", "")
        
        year = ""
        pub_parts = item.get("published-print", {}) or item.get("published-online", {})
        date_parts = pub_parts.get("date-parts", [[None]])
        if date_parts and date_parts[0] and date_parts[0][0]:
            year = str(date_parts[0][0])
        
        container = item.get("container-title", [""])[0] if item.get("container-title") else ""
        
        if title:
            results.append({
                "title": title,
                "authors": authors[:5],
                "doi": doi,
                "year": year,
                "journal": container,
                "url": f"https://doi.org/{doi}" if doi else "",
            })
    
    return results


async def recommend_similar_papers(
    keywords: List[Dict[str, float]],
    num_results: int = 5,
) -> List[Dict]:
    """
    Recommend similar papers based on extracted keywords.
    
    Args:
        keywords: List of {keyword, score} from extract_keywords()
        num_results: Number of results to return
    
    Returns:
        List of paper recommendations with title, authors, doi, etc.
    """
    if not keywords:
        return []
    
    # Build search query from top keywords (max 5 keywords for query)
    top_keywords = [k["keyword"] for k in keywords[:5]]
    query = " ".join(top_keywords)
    
    # Search Crossref
    results = await _search_crossref_async(query, rows=num_results * 2)
    
    # Remove duplicates by DOI
    seen_dois = set()
    unique_results = []
    for r in results:
        if r["doi"] and r["doi"] in seen_dois:
            continue
        if r["doi"]:
            seen_dois.add(r["doi"])
        unique_results.append(r)
        if len(unique_results) >= num_results:
            break
    
    return unique_results


def recommend_similar_papers_sync(
    keywords: List[Dict[str, float]],
    num_results: int = 5,
) -> List[Dict]:
    """
    Synchronous version of recommend_similar_papers.
    Uses multiple fallback queries for better results.
    """
    if not keywords:
        return []
    
    # Build queries - try different combinations of keywords
    top_keywords = [k["keyword"] for k in keywords[:5]]
    
    # Try: all top 5 keywords
    query = " ".join(top_keywords)
    results = _search_crossref_sync(query, rows=num_results * 2)
    
    # If no results, try with top 3 keywords (more generic)
    if not results and len(top_keywords) > 3:
        query = " ".join(top_keywords[:3])
        results = _search_crossref_sync(query, rows=num_results * 2)
    
    # If still no results, try with just the #1 keyword
    if not results and top_keywords:
        query = top_keywords[0]
        results = _search_crossref_sync(query, rows=num_results * 2)
    
    seen_dois = set()
    unique_results = []
    for r in results:
        if r["doi"] and r["doi"] in seen_dois:
            continue
        if r["doi"]:
            seen_dois.add(r["doi"])
        unique_results.append(r)
        if len(unique_results) >= num_results:
            break
    
    return unique_results
