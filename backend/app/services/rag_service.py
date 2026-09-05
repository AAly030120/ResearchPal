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
from app.services.storage import materialize_file

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


# ── Parent-child chunking ─────────────────────────────────────────────
def _split_paras(text: str) -> List[str]:
    return [p for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text)]


def _split_to_size(para: str, size: int, overlap: int) -> List[str]:
    """Split a single paragraph into <=size pieces (sentence-aware) with overlap."""
    if len(para) <= size:
        return [para]
    sentences = [s for s in re.split(r"(?<=[。.!?！？；;\n])", para) if s.strip()]
    if not sentences:
        sentences = [para]
    out: List[str] = []
    cur = ""
    for seg in sentences:
        if len(seg) > size:
            if cur:
                out.append(cur)
                cur = ""
            for i in range(0, len(seg), size):
                out.append(seg[i : i + size])
            continue
        if len(cur) + len(seg) + 1 <= size:
            cur = (cur + "\n" + seg).strip() if cur else seg
        else:
            if cur:
                out.append(cur)
            cur = seg
    if cur:
        out.append(cur)
    if overlap > 0 and len(out) > 1:
        res = [out[0]]
        for i in range(1, len(out)):
            prev = out[i - 1]
            tail = prev[-overlap:] if len(prev) > overlap else prev
            res.append(tail + "\n" + out[i])
        out = res
    return [o for o in out if o.strip()]


def chunk_parent_child(
    text: str,
    child_size: int = None,
    parent_size: int = None,
    overlap: int = None,
    pages: List[str] = None,
) -> List[dict]:
    """Parent-child chunking for better retrieval + grounded generation.

    Produces many small ``child`` chunks (embedded, used for vector retrieval)
    each paired with its ``parent`` (the paragraph it came from, used as the
    context window returned to the LLM). When ``pages`` is supplied, the source
    page number is tracked per chunk for page-level citations.

    Returns a list of {"child", "parent", "page"} dicts.
    """
    child_size = child_size or settings.RAG_CHILD_SIZE
    parent_size = parent_size or settings.RAG_PARENT_SIZE
    overlap = overlap or settings.RAG_CHUNK_OVERLAP

    text = (text or "").strip()
    if not text:
        return []

    if pages:
        paras: List[str] = []
        page_of: List[int] = []
        for pi, pt in enumerate(pages, 1):
            for p in _split_paras(pt):
                if p.strip():
                    paras.append(p.strip())
                    page_of.append(pi)
    else:
        paras = [p.strip() for p in _split_paras(text) if p.strip()]
        page_of = [0] * len(paras)

    items: List[dict] = []
    for p, pg in zip(paras, page_of):
        parent = p if len(p) <= parent_size else p[:parent_size]
        for child in _split_to_size(p, child_size, overlap):
            items.append({"child": child, "parent": parent, "page": pg})
    return items


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
    if min_score is None:
        min_score = settings.RAG_MIN_SCORE

    # ── Preferred: cross-encoder reranking ──
    from app.services.reranker import reranker as ce_reranker

    if ce_reranker.available:
        docs = [h.get("document", "") for h in hits]
        ce_scores = ce_reranker.rerank(query, docs)
        if ce_scores is not None and len(ce_scores) == len(hits):
            scored = []
            for h, s in zip(hits, ce_scores):
                if s < min_score:
                    continue
                scored.append((float(s), h))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [h for _, h in scored[:top_n]]

    # ── Fallback: heuristic (cosine similarity + jieba keyword overlap) ──
    if vector_weight is None:
        vector_weight = settings.RAG_VECTOR_WEIGHT
    if keyword_weight is None:
        keyword_weight = settings.RAG_KEYWORD_WEIGHT

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
            page = meta.get("page", 0) or 0
            # Prefer the larger parent context; fall back to the child text.
            text = meta.get("parent_text") or h.get("document", "")
            loc = f"第{page}页 " if page else ""
            label = f"[来源: {name} {loc}#片段{idx + 1}]".replace("  ", " ").strip()
            parts.append(f"{text}\n{label}")
            sources.append(
                {
                    "file": name,
                    "chunk": idx + 1,
                    "page": page,
                    "file_id": meta.get("file_id"),
                    "id": h.get("id"),
                    "text": text[:300],
                }
            )
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
                parsed = extract_text(fr.id, materialize_file(fr), fr.file_type)
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
            # Parent-child chunking (page-aware when the parser exposes pages).
            items = chunk_parent_child(text, pages=parsed.get("pages"))
            if not items:
                fr.indexed = False
                fr.chunks_count = 0
                db.commit()
                return 0
            children = [it["child"] for it in items]
            parents = [it["parent"] for it in items]
            pages_l = [it["page"] for it in items]
            embeddings = self.embedding_service.embed(children)
            self.vector_store.add_document(
                fr.user_id,
                fr.id,
                fr.original_name,
                children,
                embeddings,
                parent_texts=parents,
                pages=pages_l,
            )
            fr.indexed = True
            fr.chunks_count = len(children)
            db.commit()
            return len(children)
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

    def heal_indexes(self) -> int:
        """Re-index files flagged ``indexed`` but missing vectors.

        After an ephemeral-disk restart the Chroma store is wiped while the
        Postgres rows (and the file BLOBs) survive — so we rebuild vectors from
        the restored on-disk copies. Returns the number of files re-indexed.
        """
        from app.models.database import SessionLocal
        from app.models import File

        db = SessionLocal()
        healed = 0
        try:
            flagged = (
                db.query(File)
                .filter(File.indexed == True, File.file_type.in_(INDEXABLE_TYPES))
                .all()
            )
            for f in flagged:
                try:
                    if self.vector_store.count_for_file(f.user_id, f.id) == 0:
                        self.index_file_sync(f.id)
                        healed += 1
                except Exception as e:
                    logger.warning("heal_indexes: reindex failed for %s: %s", f.id, e)
        finally:
            db.close()
        if healed:
            logger.info("heal_indexes: re-indexed %d files", healed)
        return healed


rag_service = RAGService()
