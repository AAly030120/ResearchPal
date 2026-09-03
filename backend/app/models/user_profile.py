"""
User Profile model — persists user preferences, style fingerprints, and usage history.
Updated automatically as users interact with tools.
"""
import uuid
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # ── Preferences ──
    preferred_model = Column(String(50), default=None)
    preferred_language = Column(String(10), default="zh")  # zh / en
    preferred_ppt_style = Column(String(20), default="minimal")

    # ── Usage stats ──
    total_tasks = Column(Integer, default=0)
    total_chats = Column(Integer, default=0)
    summarizations = Column(Integer, default=0)
    ppt_generations = Column(Integer, default=0)
    analyses = Column(Integer, default=0)
    code_generations = Column(Integer, default=0)
    translations = Column(Integer, default=0)

    # ── Style fingerprint (JSON) ──
    # { "domains": ["机器学习", "数据分析"], "topics": [...], "formality": "academic",
    #   "preferred_detail_level": "detailed", "common_file_types": ["pdf", "csv"] }
    style_profile = Column(Text, default="{}")

    # ── Recent context (JSON list of last N task summaries) ──
    recent_context = Column(Text, default="[]")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="profile")
