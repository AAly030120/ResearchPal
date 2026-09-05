"""
RAG management API.

All endpoints require authentication and are scoped to the current user.
  GET  /api/rag/status        – provider, per-file index status, totals
  POST /api/rag/index/{id}    – (re)index a single file
  POST /api/rag/index-all     – index all indexable files for the user
  DELETE /api/rag/index/{id}  – remove a file's vectors from the store
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models import File
from app.services.rag_service import rag_service, INDEXABLE_TYPES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/status")
async def rag_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    files = db.query(File).filter(File.user_id == current_user.id).all()
    return {
        "provider": rag_service.embedding_service.provider,
        "model": rag_service.embedding_service.model_name,
        "dimension": rag_service.embedding_service.dimension,
        "indexable_types": sorted(INDEXABLE_TYPES),
        "total_indexed_chunks": sum(f.chunks_count or 0 for f in files),
        "indexed_files": sum(1 for f in files if f.indexed),
        "files": [
            {
                "id": f.id,
                "original_name": f.original_name,
                "file_type": f.file_type,
                "indexable": f.file_type in INDEXABLE_TYPES,
                "indexed": bool(f.indexed),
                "chunks_count": f.chunks_count or 0,
            }
            for f in files
        ],
    }


@router.post("/index/{file_id}")
async def index_file(file_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fr = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not fr:
        raise HTTPException(status_code=404, detail="File not found")
    if fr.file_type not in INDEXABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"File type '{fr.file_type}' is not indexable")
    try:
        chunks = await rag_service.index_file_async(file_id)
        db.refresh(fr)
        return {
            "file_id": fr.id,
            "original_name": fr.original_name,
            "chunks": fr.chunks_count or 0,
            "indexed": bool(fr.indexed),
            "requested_chunks": chunks,
        }
    except Exception as e:
        logger.error("Index failed for %s: %s", file_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@router.post("/index-all")
async def index_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    files = db.query(File).filter(File.user_id == current_user.id).all()
    results = []
    for f in files:
        if f.file_type in INDEXABLE_TYPES:
            try:
                await rag_service.index_file_async(f.id)
                db.refresh(f)
                results.append({
                    "id": f.id,
                    "original_name": f.original_name,
                    "chunks": f.chunks_count or 0,
                    "indexed": bool(f.indexed),
                })
            except Exception as e:
                logger.error("index-all failed for %s: %s", f.id, e)
                results.append({"id": f.id, "original_name": f.original_name, "error": str(e)})
    return {"indexed": results}


@router.delete("/index/{file_id}")
async def remove_index(file_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fr = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not fr:
        raise HTTPException(status_code=404, detail="File not found")
    rag_service.remove_index(file_id)
    fr.indexed = False
    fr.chunks_count = 0
    db.commit()
    return {"detail": "removed", "file_id": file_id}
