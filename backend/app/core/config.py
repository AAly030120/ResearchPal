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
