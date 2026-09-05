"""
Knowledge-graph (GraphRAG) models.

Entities, relations (triples), and detected communities extracted from the user's
documents. Ported from the LitKG project and adapted to ResearchPal's per-user
Postgres/SQLite store so the graph survives the ephemeral-disk restarts.

Storing the graph in the relational DB (rather than a JSON file) keeps it
consistent with the rest of the persistence work: on Render Free the disk is
wiped on restart, but Postgres (and the file BLOBs) survive — so the KG stays
intact while only the Chroma vectors need rebuilding.
"""
import uuid
from sqlalchemy import Column, String, Integer, Float, JSON, Text

from app.models.database import Base


def _id() -> str:
    return uuid.uuid4().hex


class KGEntity(Base):
    __tablename__ = "kg_entities"

    id = Column(String(36), primary_key=True, default=_id)
    user_id = Column(String(36), index=True)
    entity_type = Column(String(32), default="Method")
    name = Column(Text)
    name_zh = Column(Text, default="")
    description = Column(Text, default="")
    properties = Column(JSON, default=dict)
    source_file_id = Column(String(36), index=True)
    source_chunk_ids = Column(JSON, default=list)
    community_id = Column(Integer, default=-1)


class KGTriple(Base):
    __tablename__ = "kg_triples"

    id = Column(String(36), primary_key=True, default=_id)
    user_id = Column(String(36), index=True)
    relation_type = Column(String(32), default="USES")
    source_name = Column(Text)
    target_name = Column(Text)
    source_entity_id = Column(String(36), index=True)
    target_entity_id = Column(String(36), index=True)
    description = Column(Text, default="")
    source_file_id = Column(String(36), index=True)
    confidence = Column(Float, default=1.0)
    llm_model = Column(String(64), default="")


class KGCommunity(Base):
    __tablename__ = "kg_communities"

    id = Column(String(36), primary_key=True, default=_id)
    user_id = Column(String(36), index=True)
    community_id = Column(Integer)
    summary = Column(Text, default="")
    entities = Column(JSON, default=list)
