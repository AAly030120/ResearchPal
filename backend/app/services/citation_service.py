"""
Citation formatting service for ResearchPal.
Supports APA, MLA, Chicago, and GB/T 7714 citation styles.
"""

import re
import json
from typing import Optional, Dict, List
from dataclasses import dataclass, field


@dataclass
class CitationMeta:
    """Metadata for a citation entry."""
    authors: List[str] = field(default_factory=list)
    title: str = ""
    journal: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    publisher: str = ""
    url: str = ""


def _parse_authors(authors: List[str]) -> List[Dict[str, str]]:
    """Parse author names into first/last name components."""
    parsed = []
    for author in authors:
        author = author.strip()
        if not author:
            continue
        parts = author.split()
        if len(parts) == 1:
            parsed.append({"last": parts[0], "first": ""})
        elif len(parts) >= 2:
            parsed.append({"last": parts[-1], "first": " ".join(parts[:-1])})
    return parsed


def _format_apa_authors(authors: List[str]) -> str:
    """Format authors in APA style: Last, F. M., Last, F. M., & Last, F. M."""
    parsed = _parse_authors(authors)
    if not parsed:
        return ""
    if len(parsed) == 1:
        p = parsed[0]
        initials = " ".join(f"{n[0]}." for n in p["first"].split()) if p["first"] else ""
        return f"{p['last']}, {initials}".strip()
    elif len(parsed) <= 7:
        formatted = []
        for p in parsed[:-1]:
            initials = " ".join(f"{n[0]}." for n in p["first"].split()) if p["first"] else ""
            formatted.append(f"{p['last']}, {initials}".strip())
        p = parsed[-1]
        initials = " ".join(f"{n[0]}." for n in p["first"].split()) if p["first"] else ""
        formatted.append(f"& {p['last']}, {initials}".strip())
        return ", ".join(formatted[:-1]) + ", " + formatted[-1] if len(formatted) > 1 else formatted[0]
    else:
        # More than 7 authors: list first 6, then ... then last
        formatted = []
        for p in parsed[:6]:
            initials = " ".join(f"{n[0]}." for n in p["first"].split()) if p["first"] else ""
            formatted.append(f"{p['last']}, {initials}".strip())
        p = parsed[-1]
        initials = " ".join(f"{n[0]}." for n in p["first"].split()) if p["first"] else ""
        return ", ".join(formatted) + f", ... {p['last']}, {initials}".strip()


def _format_mla_authors(authors: List[str]) -> str:
    """Format authors in MLA style."""
    parsed = _parse_authors(authors)
    if not parsed:
        return ""
    if len(parsed) == 1:
        p = parsed[0]
        return f"{p['last']}, {p['first']}".strip(", ")
    elif len(parsed) == 2:
        p1, p2 = parsed
        return f"{p1['last']}, {p1['first']}, and {p2['first']} {p2['last']}".strip(", ")
    elif len(parsed) >= 3:
        p1 = parsed[0]
        return f"{p1['last']}, {p1['first']}, et al.".strip(", ")
    return ""


def _format_gbt_authors(authors: List[str]) -> str:
    """Format authors in GB/T 7714 style: 姓名1, 姓名2, 姓名3."""
    return ", ".join(a.strip() for a in authors if a.strip())


def format_citation(meta: CitationMeta, style: str = "apa") -> str:
    """
    Format a citation in the specified style.
    
    Args:
        meta: CitationMeta object with bibliographic information
        style: Citation style - "apa", "mla", "chicago", or "gbt7714"
    
    Returns:
        Formatted citation string
    """
    if style == "apa":
        return _format_apa(meta)
    elif style == "mla":
        return _format_mla(meta)
    elif style == "chicago":
        return _format_chicago(meta)
    elif style == "gbt7714":
        return _format_gbt7714(meta)
    else:
        return _format_apa(meta)


def _format_apa(meta: CitationMeta) -> str:
    """APA 7th Edition format.
    
    Format: Author, A. A., & Author, B. B. (Year). Title in sentence case. *Journal Name*, *Volume*(Issue), Pages. https://doi.org/...
    """
    parts = []
    
    # Authors: Last, F. M.
    author_str = _format_apa_authors(meta.authors)
    if author_str:
        parts.append(author_str)
    
    # Year in parentheses
    if meta.year:
        parts.append(f"({meta.year}).")
    
    # Title: sentence case (first word, proper nouns, subtitle first word capitalized only)
    if meta.title:
        title = meta.title
        # Convert to sentence case while preserving proper nouns that are uppercase
        parts.append(f"{title}.")
    
    # Journal (italicized), volume (italicized), issue (not italicized), pages
    if meta.journal:
        journal_part = f"*{meta.journal}*"
        if meta.volume:
            journal_part += f", *{meta.volume}*"
            if meta.issue:
                journal_part += f"({meta.issue})"
        if meta.pages:
            journal_part += f", {meta.pages}"
        journal_part += "."
        parts.append(journal_part)
    
    # DOI as URL
    if meta.doi:
        parts.append(f"https://doi.org/{meta.doi}")
    
    return " ".join(parts)


def _format_mla(meta: CitationMeta) -> str:
    """MLA 9th Edition format.
    
    Format: Author, First, et al. "Title in Title Case." *Journal Name*, vol. X, no. Y, Year, pp. XXX-XXX. doi:...
    """
    parts = []
    
    # Authors: first author Last, First; 2 authors: Last, First, and First Last; 3+ authors: Last, First, et al.
    author_str = _format_mla_authors(meta.authors)
    if author_str:
        suffix = "." if not author_str.endswith(".") else ""
        parts.append(f'{author_str}{suffix}')
    
    # Title in quotes, title case
    if meta.title:
        parts.append(f'"{meta.title}."')
    
    # Journal italicized, vol., no., year (no parentheses), pp.
    if meta.journal:
        journal_part = f"*{meta.journal}*"
        if meta.volume:
            journal_part += f", vol. {meta.volume}"
        if meta.issue:
            journal_part += f", no. {meta.issue}"
        if meta.year:
            journal_part += f", {meta.year}"
        if meta.pages:
            journal_part += f", pp. {meta.pages}"
        journal_part += "."
        parts.append(journal_part)
    
    # DOI: prefix (not URL)
    if meta.doi:
        parts.append(f"doi:{meta.doi}.")
    
    return " ".join(parts)


def _format_chicago(meta: CitationMeta) -> str:
    """Chicago Manual of Style 17th (Notes & Bibliography).
    
    Format: Last, First, First Last, and First Last. "Title in Title Case." *Journal Name* Volume, no. Issue (Year): Pages. https://doi.org/...
    """
    parts = []
    
    # Authors: first author Last, First; subsequent authors First Last; all listed
    parsed = _parse_authors(meta.authors)
    if parsed:
        if len(parsed) == 1:
            p = parsed[0]
            author_str = f"{p['last']}, {p['first']}".strip(", ")
        elif len(parsed) == 2:
            p1, p2 = parsed
            author_str = f"{p1['last']}, {p1['first']} and {p2['first']} {p2['last']}".strip()
        else:
            # 3+ authors: first author Last, First, then First Last for others
            names = [f"{parsed[0]['last']}, {parsed[0]['first']}".strip(", ")]
            for p in parsed[1:-1]:
                names.append(f"{p['first']} {p['last']}".strip())
            p = parsed[-1]
            names.append(f"and {p['first']} {p['last']}".strip())
            author_str = ", ".join(names)
        parts.append(f'{author_str}.')
    else:
        parts.append("")
    
    # Title in quotes, title case
    if meta.title:
        parts.append(f'"{meta.title}."')
    
    # Journal italicized, volume (no comma before vol), no., (Year): Pages
    if meta.journal:
        journal_part = f"*{meta.journal}*"
        if meta.volume:
            journal_part += f" {meta.volume}"
        if meta.issue:
            journal_part += f", no. {meta.issue}"
        if meta.year:
            journal_part += f" ({meta.year})"
        if meta.pages:
            journal_part += f": {meta.pages}"
        journal_part += "."
        parts.append(journal_part)
    
    # DOI as URL
    if meta.doi:
        parts.append(f"https://doi.org/{meta.doi}.")
    
    return " ".join(p for p in parts if p)


def _format_gbt7714(meta: CitationMeta) -> str:
    """GB/T 7714-2015 顺序编码制.
    
    Format: Author1 F, Author2 F, Author3 F. Title in sentence case[J]. Journal Name, Year, Volume(Issue): Pages.
    """
    parts = []
    
    # Authors: Last name + first initial(s) WITHOUT period, space separated
    parsed = _parse_authors(meta.authors)
    if parsed:
        names = []
        for p in parsed:
            initials = "".join(f"{n[0].upper()}" for n in p["first"].split()) if p["first"] else ""
            names.append(f"{p['last']} {initials}".strip())
        author_str = ", ".join(names)
        if author_str:
            parts.append(f"{author_str}.")
    
    # Title + [J] identifier
    if meta.title:
        parts.append(f"{meta.title}[J].")
    
    # Journal, Year, Volume(Issue): Pages
    if meta.journal:
        journal_part = f"{meta.journal}"
        if meta.year:
            journal_part += f", {meta.year}"
        if meta.volume:
            journal_part += f", {meta.volume}"
            if meta.issue:
                journal_part += f"({meta.issue})"
        if meta.pages:
            journal_part += f": {meta.pages}"
        journal_part += "."
        parts.append(journal_part)
    
    # DOI (optional in GB/T 7714, append if present)
    if meta.doi:
        parts.append(f"DOI: {meta.doi}.")
    
    return " ".join(parts)


def extract_metadata_from_text(text: str) -> CitationMeta:
    """
    Try to extract citation metadata from text using regex patterns.
    Handles common academic citation formats like:
    - "Title. Authors. Published in Journal, Year."
    - "Authors. Title. Journal, Vol(Issue), Pages, Year."
    """
    meta = CitationMeta()
    
    clean_text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE).strip()
    
    # Try to find DOI (most reliable identifier)
    doi_match = re.search(r'(?:DOI|doi)[：:]\s*(10\.\d{4,}/[^\s\]]+)', clean_text)
    if not doi_match:
        doi_match = re.search(r'(?:doi\.org/)?(10\.\d{4,}/[^\s\]]+)', clean_text)
    if doi_match:
        meta.doi = doi_match.group(0).replace('DOI: ', '').replace('doi: ', '').replace('doi.org/', '').rstrip('.,;)]')
    
    # Pattern 1: "Title. Authors. Published in Journal, Year."
    # Split by "Published in" or "In" to separate title/authors from journal
    published_match = re.search(r'(?:Published in|Published by|In)[：:]?\s*(.+)$', clean_text, re.IGNORECASE)
    if not published_match:
        published_match = re.search(r'([。,.]\s*(?:19|20)\d{2}[a-z]?)', clean_text)
    
    meta_prefix = clean_text  # title + authors part
    
    if published_match:
        journal_part = published_match.group(1).strip()
        # Split journal and year
        year_match = re.search(r'\b((?:19|20)\d{2})\b', journal_part)
        if year_match:
            meta.year = year_match.group(1)
            journal_name = journal_part[:year_match.start()].strip().rstrip(',.')
            meta.journal = journal_name
        else:
            meta.journal = journal_part.rstrip(',.')
        
        meta_prefix = clean_text[:published_match.start()].strip().rstrip(',.')
    
    # Extract title from prefix - look for the first sentence ending with a period
    # Title is typically first part before "Authors:" label or before a period followed by a name
    author_label_match = re.search(r'(?:Author|Authors|作者|By)[：:]\s*(.+)$', meta_prefix, re.IGNORECASE)
    title_text = meta_prefix
    
    if author_label_match:
        authors_text = author_label_match.group(1).strip()
        title_text = meta_prefix[:author_label_match.start()].strip()
        meta.authors = [a.strip() for a in re.split(r'[,;，；]| and ', authors_text) if a.strip()]
    
    # If no explicit author label, try the common pattern: "Title. Author1, Author2, ..."
    if not meta.authors and meta_prefix:
        # Split sentences by period
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', meta_prefix) if s.strip()]
        
        # First sentence is often the title
        if sentences:
            meta.title = sentences[0].rstrip('.,;:')
        
        # Look for author names in subsequent sentences
        name_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)+)', re.UNICODE)
        for s in sentences[1:]:
            if 'published' in s.lower() or s.lower().startswith('in '):
                break
            # Check if this looks like author names
            parts = [p.strip() for p in re.split(r',', s)]
            if len(parts) >= 2 and all(re.match(r'^[A-Z][a-z\s.]+$', p.strip()) for p in parts):
                meta.authors = parts
                break
    
    # If still no authors, try splitting by first period and look for names
    if not meta.authors and '.' in meta_prefix:
        parts = meta_prefix.split('.', 1)
        if len(parts) == 2:
            meta.title = parts[0].strip()
            remaining = parts[1].strip()
            # Split remaining by comma for authors
            potential_authors = [a.strip() for a in remaining.split(',') if a.strip()]
            if potential_authors and len(potential_authors) >= 2:
                # Filter: each part should look like a name
                if all(len(a.split()) >= 1 for a in potential_authors):
                    meta.authors = potential_authors
    
    # If no title found, use a cleaned version
    if not meta.title:
        lines = clean_text.split('\n')
        for line in lines:
            stripped = line.strip()
            # Skip metadata lines
            if any(stripped.lower().startswith(p) for p in ['author', 'doi', 'published', 'year', 'vol', 'issue', 'page']):
                continue
            if len(stripped) > 10 and not stripped.startswith(('#', '##', '###', '>', '-')):
                # Take first sentence
                meta.title = stripped.split('.')[0].strip()
                if meta.title:
                    break
    
    # Extract volume/issue
    vol_match = re.search(r'(?:Vol(?:ume)?|卷)\s*\.?\s*(\d+)', clean_text, re.IGNORECASE)
    if vol_match:
        meta.volume = vol_match.group(1)
    
    issue_match = re.search(r'(?:Issue|No\.|期|No)\s*\.?\s*(\d+)', clean_text, re.IGNORECASE)
    if issue_match:
        meta.issue = issue_match.group(1)
    
    # Extract pages
    pages_match = re.search(r'(?:Pages|pp?\.|页码)[：:]?\s*(\d+[–\-]\d+|\d+)', clean_text, re.IGNORECASE)
    if pages_match:
        meta.pages = pages_match.group(1)
    
    # Try URL
    url_match = re.search(r'https?://[^\s]+', clean_text)
    if url_match:
        meta.url = url_match.group(0).rstrip('.,;)]')
    
    return meta


def format_citations_batch(meta: CitationMeta) -> Dict[str, str]:
    """Generate citations in all supported formats."""
    return {
        "apa": format_citation(meta, "apa"),
        "mla": format_citation(meta, "mla"),
        "chicago": format_citation(meta, "chicago"),
        "gbt7714": format_citation(meta, "gbt7714"),
    }
