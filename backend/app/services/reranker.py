"""
Cross-encoder reranker for RAG retrieval.

Uses fastembed's ``Reranker`` (default BAAI/bge-reranker-v2-m3) to re-score the
vector-retrieved candidates against the query. Cross-encoders measure the
relatedness of (query, passage) pairs directly and consistently beat the
cosine+keyword heuristic for top-N selection.

If fastembed or the reranker model cannot be loaded (offline, no wheel, OOM),
``rerank`` returns ``None`` and the caller falls back to the heuristic rerank.
"""
import logging
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(self):
        self._model = None
        self._available: Optional[bool] = None

    def _ensure(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from fastembed import Reranker

            logger.info("Loading cross-encoder reranker: %s", settings.RAG_RERANKER_MODEL)
            self._model = Reranker(model_name=settings.RAG_RERANKER_MODEL)
            self._available = True
        except Exception as e:  # pragma: no cover - environment dependent
            logger.warning("Cross-encoder reranker unavailable, will use heuristic: %s", e)
            self._available = False
        return self._available

    @property
    def available(self) -> bool:
        return self._ensure()

    def rerank(self, query: str, documents: List[str]) -> Optional[List[float]]:
        """Return a score per document (higher = more relevant), or None on failure."""
        if not documents or not self._ensure():
            return None
        try:
            # fastembed Reranker API: rerank(query, documents) -> List[float]
            scores = self._model.rerank(query, documents)
            if scores is None:
                return None
            try:
                return [float(s) for s in scores]
            except TypeError:
                # Some versions return a list of (index, score) or score objects.
                return [float(getattr(s, "score", s)) for s in scores]
        except Exception as e:  # pragma: no cover
            logger.warning("Cross-encoder rerank call failed, using heuristic: %s", e)
            return None


reranker = CrossEncoderReranker()
