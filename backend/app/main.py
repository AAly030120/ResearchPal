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
from app.models import File, Task, Conversation, Message, UserProfile  # noqa: ensure models are registered
from app.models.user import User
from app.api import auth, files, tasks, chat, settings as settings_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Anti-abuse: global in-memory rate limit. Per-route limits can be added later.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # SQLite-specific migrations (skip for PostgreSQL — use Alembic instead)
    if settings.is_sqlite:
        from sqlalchemy import text
        migrations = [
            ("ALTER TABLE messages ADD COLUMN file_id VARCHAR(36) REFERENCES files(id)", "file_id on messages"),
            ("ALTER TABLE files ADD COLUMN version INTEGER DEFAULT 1", "version on files"),
            ("ALTER TABLE files ADD COLUMN version_group VARCHAR(36)", "version_group on files"),
        ]
        with engine.connect() as conn:
            for sql, name in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Migration OK: {name}")
                except Exception:
                    pass  # column already exists
    logger.info("Database tables ready.")
    yield


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
