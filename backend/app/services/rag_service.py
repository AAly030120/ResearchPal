"""
RAG orchestration: chunking, indexing, retrieval, hybrid reranking.

Pipeline:
  index  : extract_text → chunk → embed → store in Chroma (per user/file)
  query  : embed query → vector search (Chroma, user-scoped) → hybrid rerank
           (cosine similarity + jieba keyword overlap) → top-N context w/ citations

Indexable content types are text-like documents (PDF/DOCX/TXT/MD/PPTX). Tabular
and binary files are skipped (they are still usable via the legacy full-text path).
"""
import asyncio
import logging
import re
from typing import List, Optional, Tuple

import jieba

from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)

# File types we can meaningfully embed & retrieve from.
INDEXABLE_TYPES = {"pdf", "docx", "txt", "md", "pptx"}

# Re-export for convenience
INDEXABLE_TYPES_SET = INDEXABLE_TYPES


# ── Chunking ──────────────────────────────────────────────────────────
def chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None,
) -> List[str]:
    """Paragraph-aware chunker with sliding overlap.

    Paragraphs are packed greedily up to chunk_size; over-long paragraphs are split
    on sentence punctuation (and, as a last resort, hard character splits) so no
    content is ever dropped. Consecutive chunks share an overlapping tail.
    """
    if chunk_size is None:
        chunk_size = settings.RAG_CHUNK_SIZE
    if overlap is None:
        overlap = settings.RAG_CHUNK_OVERLAP

    text = (text or "").strip()
    if not text:
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text) if p.strip()]
    if not paras:
        paras = [text]

    # Atomic segments: paragraphs, but over-long paragraphs split into sentences.
    segments: List[str] = []
    for p in paras:
        if len(p) <= chunk_size:
            segments.append(p)
            continue
        sentences = [s for s in re.split(r"(?<=[。.!?！？；;\n])", p) if s.strip()]
        if not sentences:
            sentences = [p]
        segments.extend(sentences)

    # Greedily pack segments into chunks; hard-split any single segment > chunk_size.
    chunks: List[str] = []
    cur = ""
    for seg in segments:
        if len(seg) > chunk_size:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(seg), chunk_size):
                chunks.append(seg[i : i + chunk_size])
            continue
        if len(cur) + len(seg) + 1 <= chunk_size:
            cur = (cur + "\n" + seg).strip() if cur else seg
        else:
            if cur:
                chunks.append(cur)
            cur = seg
    if cur:
        chunks.append(cur)

    # Apply sliding overlap between consecutive chunks.
    if overlap > 0 and len(chunks) > 1:
        overlapped: List[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            tail = prev[-overlap:] if len(prev) > overlap else prev
            overlapped.append(tail + "\n" + chunks[i])
        chunks = overlapped

    return [c for c in chunks if c.strip()]


# ── Hybrid reranking ───────────────────────────────────────────────────
def _tokenize(text: str) -> set:
    return {
        t
        for t in jieba.cut(text or "")
        if t and (len(t.strip()) > 1 or (t.strip().isascii() and len(t.strip()) >= 2))
    }


def rerank(
    query: str,
    hits: List[dict],
    top_n: int = None,
    vector_weight: float = None,
    keyword_weight: float = None,
    min_score: float = None,
) -> List[dict]:
    if top_n is None:
        top_n = settings.RAG_TOP_N
    if vector_weight is None:
        vector_weight = settings.RAG_VECTOR_WEIGHT
    if keyword_weight is None:
        keyword_weight = settings.RAG_KEYWORD_WEIGHT
    if min_score is None:
        min_score = settings.RAG_MIN_SCORE

    q_tokens = _tokenize(query)
    scored = []
    for h in hits:
        dist = h.get("distance", 1.0)
        # Chroma cosine space returns distance = 1 - cosine_similarity, so the
        # normalized similarity is simply (1 - distance), clamped to [0, 1].
        sim = max(0.0, 1.0 - dist)
        doc_tokens = _tokenize(h.get("document", ""))
        overlap = len(q_tokens & doc_tokens)
        kw_score = overlap / (len(q_tokens) or 1)
        score = vector_weight * sim + keyword_weight * kw_score
        if score < min_score:
            continue  # drop clearly-irrelevant chunks (noise gate)
        scored.append((score, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored[:top_n]]


# ── Retrieval ──────────────────────────────────────────────────────────
class RAGService:
    def __init__(self):
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def has_documents(self, user_id: str) -> bool:
        try:
            return self.vector_store.count_for_user(user_id) > 0
        except Exception:
            return False

    def retrieve(
        self,
        user_id: str,
        query: str,
        file_ids: Optional[List[str]] = None,
        top_k: int = None,
        top_n: int = None,
    ) -> List[dict]:
        if not self.has_documents(user_id):
            return []
        if top_k is None:
            top_k = settings.RAG_TOP_K
        qvec = self.embedding_service.embed_query(query)
        hits = self.vector_store.search(user_id, qvec, top_k=top_k, file_ids=file_ids)
        if not hits:
            return []
        return rerank(query, hits, top_n=top_n)

    def format_context(self, hits: List[dict]) -> Tuple[str, List[dict]]:
        parts: List[str] = []
        sources: List[dict] = []
        for h in hits:
            meta = h.get("metadata", {})
            name = meta.get("original_name", "文档")
            idx = meta.get("chunk_index", 0)
            label = f"[来源: {name} #片段{idx + 1}]"
            parts.append(f"{h.get('document', '')}\n{label}")
            sources.append({"file": name, "chunk": idx + 1, "id": h.get("id")})
        return "\n\n".join(parts), sources

    # ── Indexing ──────────────────────────────────────────────────────
    def index_file_sync(self, file_id: str) -> int:
        """Blocking index of a single file. Opens its own DB session."""
        from app.models.database import SessionLocal
        from app.models import File
        from app.services.file_parser import extract_text

        db = SessionLocal()
        try:
            fr = db.query(File).filter(File.id == file_id).first()
            if not fr:
                logger.warning("index_file: file %s not found", file_id)
                return 0
            if fr.file_type not in INDEXABLE_TYPES:
                fr.indexed = False
                fr.chunks_count = 0
                db.commit()
                return 0
            try:
                parsed = extract_text(fr.id, fr.storage_path, fr.file_type)
            except Exception as e:
                logger.warning("index_file extract failed for %s: %s", file_id, e)
                fr.indexed = False
                fr.chunks_count = 0
                db.commit()
                return 0
            text = parsed.get("text", "")
            if not text or not text.strip():
                fr.indexed = False
                fr.chunks_count = 0
                db.commit()
                return 0
            chunks = chunk_text(text)
            if not chunks:
                fr.indexed = False
                fr.chunks_count = 0
                db.commit()
                return 0
            embeddings = self.embedding_service.embed(chunks)
            self.vector_store.add_document(
                fr.user_id, fr.id, fr.original_name, chunks, embeddings
            )
            fr.indexed = True
            fr.chunks_count = len(chunks)
            db.commit()
            return len(chunks)
        finally:
            db.close()

    async def index_file_async(self, file_id: str) -> int:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.index_file_sync, file_id)

    def schedule_index(self, file_id: str) -> None:
        """Fire-and-forget indexing from a request handler (runs after response)."""
        try:
            asyncio.create_task(self.index_file_async(file_id))
        except Exception as e:
            logger.warning("schedule_index failed for %s: %s", file_id, e)

    def remove_index(self, file_id: str) -> None:
        self.vector_store.delete_document(file_id)


rag_service = RAGService()
