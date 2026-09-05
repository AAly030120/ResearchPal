import os
import uuid
import json
import shutil
import logging
from typing import Optional
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse as FastAPIFileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models import File
from app.schemas.file import (
    FileResponse,
    ChunkStartRequest,
    ChunkStartResponse,
    ChunkCompleteRequest,
    FileVersionInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


def _schedule_indexing(file_id: str) -> None:
    """Kick off background RAG indexing for a freshly uploaded file.

    Runs after the HTTP response is returned (fire-and-forget) so uploads stay
    fast. Failures are logged and do not affect the upload result.
    """
    try:
        from app.services.rag_service import rag_service
        rag_service.schedule_index(file_id)
    except Exception as e:
        logger.warning(f"Could not schedule indexing for {file_id}: {e}")

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".csv",
    ".xlsx", ".xls", ".py", ".json", ".log", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".html",
}

# ── In-memory chunked upload session tracker ─────────────────────────
_chunk_sessions: dict = {}   # upload_id -> {filename, total_chunks, chunks_dir, received_chunks, file_size, chunk_size}
_chunk_lock = Lock()

CHUNK_SIZE = 5 * 1024 * 1024   # 5 MB per chunk


def _get_user_upload_dir(user_id: str) -> str:
    d = os.path.join(settings.UPLOAD_DIR, user_id)
    os.makedirs(d, exist_ok=True)
    return d


# ── Chunked Upload ───────────────────────────────────────────────────

@router.post("/chunk/start", response_model=ChunkStartResponse)
async def chunk_upload_start(
    body: ChunkStartRequest,
    current_user: User = Depends(get_current_user),
):
    """Initialise a chunked upload session. Returns upload_id."""
    ext = os.path.splitext(body.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    if body.file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50 MB)")

    upload_id = uuid.uuid4().hex
    chunks_dir = os.path.join(settings.UPLOAD_DIR, "chunks", current_user.id, upload_id)
    os.makedirs(chunks_dir, exist_ok=True)

    with _chunk_lock:
        _chunk_sessions[upload_id] = {
            "filename": body.filename,
            "total_chunks": body.total_chunks,
            "chunks_dir": chunks_dir,
            "received_chunks": set(),
            "file_size": body.file_size,
            "chunk_size": CHUNK_SIZE,
        }

    logger.info(f"Chunked upload started: upload_id={upload_id} file={body.filename}")
    return ChunkStartResponse(upload_id=upload_id)


@router.post("/chunk/complete", response_model=FileResponse)
async def chunk_upload_complete(
    body: ChunkCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merge all chunks into the final file and create a database record."""
    with _chunk_lock:
        session = _chunk_sessions.pop(body.upload_id, None)

    if not session:
        raise HTTPException(status_code=404, detail="Unknown or expired upload session")

    expected = set(range(session["total_chunks"]))
    missing = expected - session["received_chunks"]
    if missing:
        shutil.rmtree(session["chunks_dir"], ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Missing chunks: {sorted(missing)}")

    # Merge chunks
    ext = os.path.splitext(session["filename"])[1].lower()
    user_dir = _get_user_upload_dir(current_user.id)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(user_dir, stored_name)

    with open(storage_path, "wb") as final_f:
        for i in range(session["total_chunks"]):
            chunk_path = os.path.join(session["chunks_dir"], f"{i:06d}")
            with open(chunk_path, "rb") as cf:
                final_f.write(cf.read())

    # Clean up chunk directory
    shutil.rmtree(session["chunks_dir"], ignore_errors=True)

    actual_size = os.path.getsize(storage_path)
    file_type = ext.lstrip(".").lower()

    # Version tracking: find previous versions with same original name
    version_group = uuid.uuid4().hex
    prev_versions = (
        db.query(File)
        .filter(File.user_id == current_user.id, File.original_name == session["filename"])
        .order_by(File.version.desc())
        .all()
    )
    if prev_versions:
        version_group = prev_versions[0].version_group or version_group
        new_version = prev_versions[0].version + 1
    else:
        new_version = 1

    file_record = File(
        user_id=current_user.id,
        filename=stored_name,
        original_name=session["filename"],
        file_type=file_type,
        file_size=actual_size,
        storage_path=storage_path,
        version=new_version,
        version_group=version_group,
    )
    # Persist raw bytes in the DB so the document survives an ephemeral-disk
    # restart (the DB itself — Postgres — outlives the local filesystem).
    try:
        with open(storage_path, "rb") as _f:
            file_record.data = _f.read()
    except OSError:
        file_record.data = None
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    logger.info(f"Chunked upload complete: {session['filename']} v{new_version}")
    _schedule_indexing(file_record.id)
    return FileResponse.model_validate(file_record)


@router.post("/chunk/{upload_id}")
async def chunk_upload_part(
    upload_id: str,
    chunk_index: int = Query(...),
    chunk: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
):
    """Receive one chunk of a file."""
    with _chunk_lock:
        session = _chunk_sessions.get(upload_id)
        if not session:
            raise HTTPException(status_code=404, detail="Unknown or expired upload session")

    chunk_path = os.path.join(session["chunks_dir"], f"{chunk_index:06d}")

    content = await chunk.read()
    with open(chunk_path, "wb") as f:
        f.write(content)

    with _chunk_lock:
        session["received_chunks"].add(chunk_index)

    return {"upload_id": upload_id, "chunk_index": chunk_index, "received": True}


# ── Simple (non-chunked) Upload ──────────────────────────────────────

@router.post("/upload", response_model=FileResponse)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    user_dir = _get_user_upload_dir(current_user.id)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(user_dir, stored_name)

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    with open(storage_path, "wb") as f:
        f.write(content)

    file_type = ext.lstrip(".").lower()

    # Version tracking
    version_group = uuid.uuid4().hex
    prev_versions = (
        db.query(File)
        .filter(File.user_id == current_user.id, File.original_name == file.filename)
        .order_by(File.version.desc())
        .all()
    )
    if prev_versions:
        version_group = prev_versions[0].version_group or version_group
        new_version = prev_versions[0].version + 1
    else:
        new_version = 1

    file_record = File(
        user_id=current_user.id,
        filename=stored_name,
        original_name=file.filename,
        file_type=file_type,
        file_size=len(content),
        storage_path=storage_path,
        version=new_version,
        version_group=version_group,
    )
    # Persist raw bytes in the DB so the document survives an ephemeral-disk
    # restart (the DB itself — Postgres — outlives the local filesystem).
    file_record.data = content
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    _schedule_indexing(file_record.id)
    return FileResponse.model_validate(file_record)


# ── List / Get / Delete ──────────────────────────────────────────────

@router.get("/", response_model=list[FileResponse])
async def list_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = db.query(File).filter(File.user_id == current_user.id).order_by(File.uploaded_at.desc()).all()
    return [FileResponse.model_validate(f) for f in files]


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_record = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse.model_validate(file_record)


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_record = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        if os.path.exists(file_record.storage_path):
            os.remove(file_record.storage_path)
    except OSError as e:
        logger.warning(f"Could not delete file from disk: {e}")

    # Remove any RAG vectors indexed from this file.
    try:
        from app.services.rag_service import rag_service
        rag_service.remove_index(file_record.id)
    except Exception as e:
        logger.warning(f"Could not remove RAG index for {file_id}: {e}")

    db.delete(file_record)
    db.commit()
    return {"detail": "File deleted"}


# ── Download ─────────────────────────────────────────────────────────

@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a file by its ID. Returns the original file with proper Content-Disposition."""
    file_record = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Materialize from DB BLOB if the on-disk copy was wiped by a restart.
    from app.services.storage import materialize_file
    resolved = materialize_file(file_record)
    if not resolved or not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File content unavailable")

    return FastAPIFileResponse(
        path=resolved,
        filename=file_record.original_name,
        media_type="application/octet-stream",
    )


# ── Preview ──────────────────────────────────────────────────────────

@router.get("/preview/{file_id}")
async def preview_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a file for inline preview (with inline Content-Disposition)."""
    file_record = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(file_record.storage_path):
        # Try to restore from DB BLOB (ephemeral-disk restart recovery).
        from app.services.storage import materialize_file
        materialize_file(file_record)

    if not os.path.exists(file_record.storage_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine media type for proper inline display
    media_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
        "txt": "text/plain",
        "md": "text/plain",
        "json": "application/json",
        "html": "text/html",
        "csv": "text/csv",
    }
    media_type = media_types.get(file_record.file_type, "application/octet-stream")

    return FastAPIFileResponse(
        path=file_record.storage_path,
        media_type=media_type,
    )


# ── Version History ──────────────────────────────────────────────────

@router.get("/versions/{file_id}", response_model=list[FileVersionInfo])
async def get_file_versions(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all versions of a file (by version_group)."""
    file_record = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_record.version_group:
        return [FileVersionInfo(
            id=file_record.id,
            version=file_record.version,
            file_size=file_record.file_size,
            uploaded_at=file_record.uploaded_at,
        )]

    versions = (
        db.query(File)
        .filter(File.version_group == file_record.version_group, File.user_id == current_user.id)
        .order_by(File.version.desc())
        .all()
    )
    return [
        FileVersionInfo(
            id=v.id,
            version=v.version,
            file_size=v.file_size,
            uploaded_at=v.uploaded_at,
        )
        for v in versions
    ]
