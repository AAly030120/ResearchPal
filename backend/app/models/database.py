from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings


def _normalize_url(raw: str) -> str:
    """Render (and some providers) hand out ``postgres://`` connection strings,
    which SQLAlchemy 2.x rejects (it expects ``postgresql://``). Normalize so the
    dialect resolves correctly.
    """
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    return raw


_url = _normalize_url(settings.DATABASE_URL)
_is_sqlite = "sqlite" in _url

# SQLite needs check_same_thread=False when used across FastAPI's threadpool;
# Postgres benefits from connection health checks and a recycle interval that
# stays under typical cloud idle timeouts (e.g. Render/PgBouncer).
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "connect_args": _connect_args,
}
if not _is_sqlite:
    _engine_kwargs["pool_recycle"] = 1800
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_engine(_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
