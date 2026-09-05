import os
from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    # ── Application ──
    APP_NAME: str = "ResearchPal"
    APP_VERSION: str = "1.0.0"

    # ── Security ──
    # SECURITY: never commit a real secret. In production (DEBUG=false) the app
    # refuses to start unless SECRET_KEY is a strong, unique value.
    # pydantic-settings reads the SECRET_KEY env var automatically; "" is the
    # safe default (dev mode runs unsigned, production must override it).
    SECRET_KEY: str = ""

    @model_validator(mode="after")
    def _enforce_production_secret(self):
        if self.is_production and not self.SECRET_KEY:
            raise ValueError(
                "SECURITY: SECRET_KEY must be set in production. "
                "Generate one with: openssl rand -hex 32"
            )
        return self

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ──
    # SQLite for local dev; PostgreSQL (postgresql://...) for production
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./researchpal.db"
    )

    # ── CORS ──
    # Comma-separated origins, e.g. "https://app.vercel.app,https://app.example.com"
    # Defaults to "*" in dev only
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # ── Debug ──
    # Dev by default so a fresh clone runs zero-config (Demo mode). Production
    # deploys must set DEBUG=false, which then forces a real SECRET_KEY.
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # ── File storage ──
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # ── LLM API Keys ──
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # ── Default model ──
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

    # ── RAG (Retrieval-Augmented Generation) ──
    # Embedding provider: "auto" (dashscope if QWEN_API_KEY present else local),
    # "local" (fastembed, offline, no API key), or "dashscope" (Aliyun text-embedding-v3).
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "auto")
    # Local embedding model (fastembed registry name). Chinese-strong, tiny (~30MB).
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    # DashScope embedding model id (compatible-mode OpenAI embeddings endpoint).
    DASHSCOPE_EMBED_MODEL: str = os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v3")
    # Persisted Chroma vector store directory (relative to backend cwd).
    CHROMA_DIR: str = os.getenv("CHROMA_DIR", os.path.join("chroma_store"))
    # Chunking
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "700"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
    # Retrieval
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "15"))        # candidates from vector store
    RAG_TOP_N: int = int(os.getenv("RAG_TOP_N", "6"))         # chunks injected after rerank
    # Hybrid rerank weights (vector similarity + jieba keyword overlap)
    RAG_VECTOR_WEIGHT: float = float(os.getenv("RAG_VECTOR_WEIGHT", "0.6"))
    RAG_KEYWORD_WEIGHT: float = float(os.getenv("RAG_KEYWORD_WEIGHT", "0.4"))
    # Minimum combined rerank score to inject a chunk as context (filters noise).
    RAG_MIN_SCORE: float = float(os.getenv("RAG_MIN_SCORE", "0.2"))

    # ── Parent-child chunking ──
    # Children are small retrieval units (embedded); parents are larger context
    # windows returned to the LLM so answers stay grounded without token bloat.
    RAG_CHILD_SIZE: int = int(os.getenv("RAG_CHILD_SIZE", "320"))
    RAG_PARENT_SIZE: int = int(os.getenv("RAG_PARENT_SIZE", "700"))

    # ── Cross-encoder reranker (optional) ──
    # When fastembed's Reranker is importable it re-ranks the vector candidates
    # with a cross-encoder; otherwise the heuristic (cosine + jieba) is used.
    RAG_RERANKER_MODEL: str = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    RAG_CROSS_ENCODER_WEIGHT: float = float(os.getenv("RAG_CROSS_ENCODER_WEIGHT", "1.0"))

    # ── Knowledge Graph (GraphRAG) ──
    # LitKG-style entity/relation extraction + graph retrieval, fused into chat.
    KG_ENABLED: bool = os.getenv("KG_ENABLED", "true").lower() == "true"
    # Model used for KG extraction / community summaries; empty => current chat model.
    KG_EXTRACTION_MODEL: str = os.getenv("KG_EXTRACTION_MODEL", "")
    KG_MAX_ENTITIES_PER_FILE: int = int(os.getenv("KG_MAX_ENTITIES_PER_FILE", "60"))
    KG_RETRIEVAL_HOPS: int = int(os.getenv("KG_RETRIEVAL_HOPS", "2"))

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL

    @property
    def is_production(self) -> bool:
        return not self.DEBUG


settings = Settings()
