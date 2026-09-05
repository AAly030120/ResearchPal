"""
Chroma-backed vector store for RAG document chunks.

Design notes:
  * One persistent Chroma client (CHROMA_DIR). Collections are keyed by
    "<provider>_<dim>" so switching embedding models never mixes vectors.
  * All chunks carry metadata: user_id, file_id, original_name, chunk_index.
  * Retrieval filters by user_id (privacy boundary) and optionally by file_id(s).
"""
import logging
import os
from typing import Dict, List, Optional

from app.core.config import settings
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

# Chroma is heavy to import; do it lazily so app startup stays fast.
_CHROMA_AVAILABLE = None


def _chroma_available() -> bool:
    global _CHROMA_AVAILABLE
    if _CHROMA_AVAILABLE is None:
        try:
            import chromadb  # noqa: F401
            _CHROMA_AVAILABLE = True
        except Exception as e:  # pragma: no cover
            logger.warning("chromadb not installed: %s", e)
            _CHROMA_AVAILABLE = False
    return _CHROMA_AVAILABLE


class VectorStore:
    def __init__(self):
        self._client = None
        self._collections: Dict[str, object] = {}

    # ── Client / collection lifecycle ────────────────────────────────
    def _get_client(self):
        if self._client is None:
            import chromadb
            os.makedirs(settings.CHROMA_DIR, exist_ok=True)
            self._client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        return self._client

    def _collection_name(self) -> str:
        return f"researchpal_{embedding_service.provider}_{embedding_service.dimension}"

    def _get_collection(self):
        if not _chroma_available():
            raise RuntimeError("chromadb is not installed; cannot use vector store")
        name = self._collection_name()
        if name not in self._collections:
            client = self._get_client()
            try:
                col = client.get_or_create_collection(
                    name=name, metadata={"hnsw:space": "cosine"}
                )
            except Exception:
                # Collection exists with different metadata — reuse as-is.
                col = client.get_collection(name=name)
            self._collections[name] = col
        return self._collections[name]

    # ── Write ────────────────────────────────────────────────────────
    def add_document(
        self,
        user_id: str,
        file_id: str,
        original_name: str,
        chunks: List[str],
        embeddings: List[List[float]],
    ) -> int:
        if not chunks:
            return 0
        col = self._get_collection()
        ids = [f"{file_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "user_id": user_id,
                "file_id": file_id,
                "original_name": original_name,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        col.upsert(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
        logger.info("Indexed %d chunks for file %s (%s)", len(chunks), file_id, original_name)
        return len(chunks)

    def delete_document(self, file_id: str) -> None:
        if not _chroma_available():
            return
        try:
            client = self._get_client()
            for col_info in client.list_collections():
                try:
                    col = client.get_collection(col_info.name)
                    col.delete(where={"file_id": file_id})
                except Exception as e:
                    logger.warning("delete_document failed on %s: %s", col_info.name, e)
        except Exception as e:
            logger.warning("delete_document error: %s", e)

    # ── Read ─────────────────────────────────────────────────────────
    def count_for_user(self, user_id: str) -> int:
        if not _chroma_available():
            return 0
        try:
            col = self._get_collection()
            res = col.get(where={"user_id": user_id}, limit=1, include=[])
            return len(res.get("ids", []))
        except Exception as e:
            logger.warning("count_for_user error: %s", e)
            return 0

    def search(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int = 15,
        file_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        if not _chroma_available():
            return []
        col = self._get_collection()
        where: dict = {"user_id": user_id}
        if file_ids:
            where["file_id"] = {"$in": file_ids}
        try:
            res = col.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning("vector search error: %s", e)
            return []
        out: List[dict] = []
        if res.get("ids") and res["ids"][0]:
            for i, doc_id in enumerate(res["ids"][0]):
                out.append(
                    {
                        "id": doc_id,
                        "document": res["documents"][0][i],
                        "metadata": res["metadatas"][0][i],
                        "distance": res["distances"][0][i],
                    }
                )
        return out


vector_store = VectorStore()
