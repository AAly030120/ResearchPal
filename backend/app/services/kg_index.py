"""
Background KG indexing: parse a file, extract entities/relations via LLM, and
persist them into the graph store. Mirrors the vector indexing flow but populates
the knowledge graph instead of Chroma.
"""
import asyncio
import logging

from app.core.config import settings
from app.models.database import SessionLocal
from app.models import File
from app.services.file_parser import extract_text
from app.services.kg_extractor import extract_kg
from app.services.kg_store import upsert_extraction
from app.services.storage import materialize_file

logger = logging.getLogger(__name__)

INDEXABLE = {"pdf", "docx", "txt", "md", "pptx"}


async def index_file(file_id: str) -> int:
    """Extract & store the knowledge graph for one file. Returns entity count."""
    if not settings.KG_ENABLED:
        return 0
    db = SessionLocal()
    try:
        fr = db.query(File).filter(File.id == file_id).first()
        if not fr:
            return 0
        if fr.file_type not in INDEXABLE:
            return 0
        loop = asyncio.get_event_loop()
        try:
            parsed = await loop.run_in_executor(
                None, lambda: extract_text(fr.id, materialize_file(fr), fr.file_type)
            )
        except Exception as e:
            logger.warning("KG index: parse failed for %s: %s", file_id, e)
            return 0
        text = parsed.get("text", "")
        if not text or not text.strip():
            return 0
        result = await extract_kg(text)
        ents, trips = result["entities"], result["triples"]
        if not ents and not trips:
            return 0
        n_e, n_t = upsert_extraction(fr.user_id, fr.id, ents, trips)
        logger.info("KG indexed file %s: %d entities, %d triples", file_id, n_e, n_t)
        return n_e
    finally:
        db.close()


def schedule_index(file_id: str) -> None:
    try:
        asyncio.create_task(index_file(file_id))
    except Exception as e:  # pragma: no cover
        logger.warning("KG schedule_index failed for %s: %s", file_id, e)
