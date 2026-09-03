import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse as FastAPIFileResponse

from app.core.config import settings
from app.models.database import engine, Base, get_db
from app.models import File, Task, Conversation, Message, UserProfile  # noqa: ensure models are registered
from app.api import auth, files, tasks, chat, settings as settings_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": "production" if settings.is_production else "development",
        "database": "postgresql" if not settings.is_sqlite else "sqlite",
    }


@app.get("/api/tasks/{task_id}/download")
async def download_task_result(task_id: str):
    """Download generated file (PPTX, translated DOCX, etc.) or text result."""
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
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
