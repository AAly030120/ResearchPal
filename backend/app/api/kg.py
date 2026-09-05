"""
Knowledge-graph (GraphRAG) API.

Status, per-file / all-file extraction, community detection, and a lightweight
graph dump for (optional) visualization.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models import File
from app.models.kg import KGEntity
from app.services import kg_index
from app.services.kg_store import detect_communities, get_graph, stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])


@router.get("/status")
async def kg_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = stats(current_user.id)
    files = (
        db.query(File)
        .filter(File.user_id == current_user.id, File.file_type.in_(kg_index.INDEXABLE))
        .all()
    )
    file_infos = []
    for f in files:
        kg_ents = (
            db.query(KGEntity)
            .filter(KGEntity.user_id == current_user.id, KGEntity.source_file_id == f.id)
            .count()
        )
        file_infos.append({
            "id": f.id,
            "name": f.original_name,
            "type": f.file_type,
            "indexed": f.indexed,
            "kg_entities": kg_ents,
            "kg_ready": kg_ents > 0,
        })
    return {
        "enabled": True,
        "stats": s,
        "files": file_infos,
    }


@router.post("/index/{file_id}")
async def kg_index_one(file_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fr = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not fr:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    n = await kg_index.index_file(file_id)
    return {"file_id": file_id, "entities": n}


@router.post("/index-all")
async def kg_index_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    files = (
        db.query(File)
        .filter(File.user_id == current_user.id, File.file_type.in_(kg_index.INDEXABLE))
        .all()
    )
    results = []
    for f in files:
        n = await kg_index.index_file(f.id)
        results.append({"file_id": f.id, "name": f.original_name, "entities": n})
    return {"indexed": len(results), "details": results}


@router.post("/communities")
async def kg_communities(current_user: User = Depends(get_current_user)):
    count = await detect_communities(current_user.id)
    return {"communities": count}


@router.get("/graph")
async def kg_graph(current_user: User = Depends(get_current_user), file_id: str = None):
    g = get_graph(current_user.id)
    nodes = []
    for n, attrs in g.nodes(data=True):
        if file_id and attrs.get("file_id") != file_id:
            continue
        nodes.append({
            "id": n,
            "name": attrs.get("name", n),
            "type": attrs.get("entity_type", ""),
            "description": attrs.get("description", ""),
        })
    edges = []
    for u, v, edata in g.edges(data=True):
        if file_id and g.nodes[u].get("file_id") != file_id and g.nodes[v].get("file_id") != file_id:
            continue
        edges.append({
            "source": u, "target": v, "relation": edata.get("relation", ""),
        })
    return {"nodes": nodes, "edges": edges}
