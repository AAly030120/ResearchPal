"""
Embedding service for RAG.

Two backends, selected at runtime:
  * "local"     → fastembed (BAAI/bge-small-zh-v1.5 by default). Runs fully offline,
                  no API key required. Best for robustness / demo mode.
  * "dashscope" → Aliyun DashScope text-embedding-v3 via the OpenAI-compatible
                  /v1/embeddings endpoint (reuses QWEN_API_KEY).

EMBEDDING_PROVIDER = "auto" (default) picks dashscope when QWEN_API_KEY is set,
otherwise falls back to local. The selected provider + its dimension are baked into
the Chroma collection name, so switching providers never mixes incompatible vectors.
"""
import logging
import os
from typing import List

from app.core.config import settings
from app.core.key_manager import key_manager

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self._mode = os.getenv("EMBEDDING_PROVIDER", settings.EMBEDDING_PROVIDER).lower()
        self._local_model_name = os.getenv("RAG_EMBEDDING_MODEL", settings.RAG_EMBEDDING_MODEL)
        self._dash_model = os.getenv("DASHSCOPE_EMBED_MODEL", settings.DASHSCOPE_EMBED_MODEL)
        self._local_model = None
        self._local_dim = None
        self._dash_dim = None
        self._resolved = False
        self._active_provider = None

    # ── Provider resolution ─────────────────────────────────────────
    def _resolve_provider(self) -> str:
        if self._resolved:
            return self._active_provider
        if self._mode == "local":
            provider = "local"
        elif self._mode == "dashscope":
            provider = "dashscope"
        else:  # auto
            provider = "dashscope" if key_manager.has("QWEN_API_KEY") else "local"
        self._active_provider = provider
        self._resolved = True
        logger.info("RAG embedding provider resolved to: %s", provider)
        return provider

    @property
    def provider(self) -> str:
        return self._resolve_provider()

    @property
    def model_name(self) -> str:
        return self._dash_model if self.provider == "dashscope" else self._local_model_name

    # ── Dimension (lazily detected) ─────────────────────────────────
    @property
    def dimension(self) -> int:
        if self.provider == "dashscope":
            if self._dash_dim is None:
                self._detect_dashscope_dim()
            return self._dash_dim
        self._ensure_local()
        return self._local_dim

    def _ensure_local(self):
        if self._local_model is None:
            from fastembed import TextEmbedding
            logger.info("Loading local embedding model: %s", self._local_model_name)
            self._local_model = TextEmbedding(model_name=self._local_model_name)
            probe = list(self._local_model.embed(["维度探测"]))
            self._local_dim = len(probe[0])
            logger.info("Local embedding dim=%d", self._local_dim)
        return self._local_model

    def _detect_dashscope_dim(self):
        try:
            resp = self._dashscope_raw(["维度探测"])
            self._dash_dim = len(resp[0])
            logger.info("DashScope embedding dim=%d", self._dash_dim)
        except Exception as e:
            logger.warning("DashScope dim detection failed (%s); defaulting to 1024", e)
            self._dash_dim = 1024

    # ── DashScope (OpenAI-compatible) ───────────────────────────────
    def _dashscope_raw(self, texts: List[str]) -> List[List[float]]:
        from openai import OpenAI
        api_key = key_manager.get("QWEN_API_KEY")
        if not api_key:
            raise ValueError("QWEN_API_KEY not configured for dashscope embeddings")
        client = OpenAI(api_key=api_key, base_url=settings.QWEN_BASE_URL, timeout=60)
        resp = client.embeddings.create(model=self._dash_model, input=texts)
        return [d.embedding for d in resp.data]

    # ── Public API ──────────────────────────────────────────────────
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts (documents OR queries) into vectors."""
        if not texts:
            return []
        if self.provider == "dashscope":
            return self._dashscope_raw(texts)
        model = self._ensure_local()
        vectors = list(model.embed(texts))
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]


embedding_service = EmbeddingService()
