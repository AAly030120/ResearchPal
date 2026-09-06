import os
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse as FastAPIFileResponse, JSONResponse

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.security import get_current_user
from app.models.database import engine, Base, get_db
from sqlalchemy import inspect
from app.models import File, Task, Conversation, Message, UserProfile  # noqa: ensure models are registered
from app.models.user import User
from app.api import auth, files, tasks, chat, settings as settings_api, rag as rag_api, kg as kg_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Anti-abuse: global in-memory rate limit. Per-route limits can be added later.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # Idempotent schema migrations — engine-agnostic. create_all() already adds
    # the columns on a fresh DB, so each ALTER is guarded by a column-existence
    # check and only runs when the column is genuinely missing.
    from sqlalchemy import text

    data_type = "BYTEA" if not settings.is_sqlite else "BLOB"
    column_adds = [
        ("messages", "file_id", "ALTER TABLE messages ADD COLUMN file_id VARCHAR(36) REFERENCES files(id)"),
        ("files", "version", "ALTER TABLE files ADD COLUMN version INTEGER DEFAULT 1"),
        ("files", "version_group", "ALTER TABLE files ADD COLUMN version_group VARCHAR(36)"),
        ("files", "indexed", "ALTER TABLE files ADD COLUMN indexed BOOLEAN DEFAULT 0"),
        ("files", "chunks_count", "ALTER TABLE files ADD COLUMN chunks_count INTEGER DEFAULT 0"),
        ("files", "data", f"ALTER TABLE files ADD COLUMN data {data_type}"),
    ]
    with engine.connect() as conn:
        for table, column, sql in column_adds:
            if _column_exists(engine, table, column):
                continue
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"Migration OK: {table}.{column}")
            except Exception as e:
                conn.rollback()
                logger.warning(f"Migration skipped for {table}.{column}: {e}")
    logger.info("Database tables ready.")

    # Self-heal RAG vectors after an ephemeral-disk restart. The Postgres rows
    # (and file BLOBs) survive, but the Chroma store is wiped — rebuild it in the
    # background so retrieval works again without manual re-indexing.
    import threading

    def _startup_heal():
        try:
            from app.services.rag_service import rag_service
            rag_service.heal_indexes()
        except Exception as e:
            logger.warning("startup RAG heal failed: %s", e)

    threading.Thread(target=_startup_heal, daemon=True).start()

    # Optional demo provisioning. Set SEED_DEMO=1 in the Render dashboard to have
    # the instance self-seed a ready-to-demo account (sample literature + graph)
    # on boot. Gated off by default; never blocks startup; failures are logged,
    # not fatal. SEED_DEMO_RESET=1 wipes and rebuilds an existing demo account.
    if os.getenv("SEED_DEMO") == "1":

        def _startup_seed():
            try:
                import importlib.util

                # scripts/ is not a package; load by path so this works regardless
                # of how the interpreter resolves namespace packages.
                seed_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "scripts",
                    "seed_demo.py",
                )
                spec = importlib.util.spec_from_file_location("seed_demo", seed_path)
                seed_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(seed_mod)
                seed_mod.run_seed(reset=os.getenv("SEED_DEMO_RESET") == "1")
            except Exception as e:  # never crash the app because of seeding
                logger.warning("startup demo seed failed (ignored): %s", e)

        threading.Thread(target=_startup_seed, daemon=True).start()
        logger.info("Demo seeding scheduled (SEED_DEMO=1)")

    yield


def _column_exists(engine, table: str, column: str) -> bool:
    """Cross-engine column existence check via SQLAlchemy inspector.

    Handles SQLite (PRAGMA-free) and Postgres uniformly and avoids the
    schema/case-sensitivity pitfalls of a hand-written information_schema query.
    """
    try:
        insp = inspect(engine)
        if not insp.has_table(table):
            return False
        return any(col["name"].lower() == column.lower() for col in insp.get_columns(table))
    except Exception:
        return False


app = FastAPI(
    title="ResearchPal API",
    version="1.0",
    lifespan=lifespan,
)

# CORS — production origins from env, dev defaults to "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True if settings.cors_origins_list != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(files.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(settings_api.router)
app.include_router(rag_api.router)
app.include_router(kg_api.router)

# Apply global rate limiting middleware (in-memory; safe for single-instance deploy)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"success": False, "detail": "Too many requests, please slow down."},
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    """Unified error contract: never leak internal tracebacks in production."""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    detail = f"{type(exc).__name__}: {exc}" if settings.DEBUG else "Internal server error"
    return JSONResponse(status_code=500, content={"success": False, "detail": detail})


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": "production" if settings.is_production else "development",
        "database": "postgresql" if not settings.is_sqlite else "sqlite",
    }


@app.get("/api/tasks/{task_id}/download")
async def download_task_result(task_id: str, current_user: User = Depends(get_current_user)):
    """Download generated file (PPTX, translated DOCX, etc.) or text result.
    Requires authentication and ownership of the task."""
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        # Authorization: only the owner may download their generated artifacts
        if task.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this resource")
        if not task.result_path:
            if task.result_text:
                from fastapi.responses import Response
                return Response(
                    content=task.result_text,
                    media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={task.task_type}_result.txt"},
                )
            raise HTTPException(status_code=404, detail="No result file")
        file_path = task.result_path
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        # Guard against path traversal: confine to the backend working directory
        file_path = os.path.normpath(file_path)
        base_dir = os.path.abspath(os.getcwd())
        if not (file_path == base_dir or file_path.startswith(base_dir + os.sep)):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Result file not found on disk")
        filename = os.path.basename(file_path)
        return FastAPIFileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream",
        )
    finally:
        db.close()
