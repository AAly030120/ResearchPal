import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, func
from app.models.database import Base

def gen_uuid():
    return str(uuid.uuid4())

class File(Base):
    __tablename__ = "files"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    file_type = Column(String(50))
    file_size = Column(Integer)
    storage_path = Column(String(500), nullable=False)
    uploaded_at = Column(DateTime, default=func.now())
    version = Column(Integer, default=1)
    # group key for same-original-name files to track version history
    version_group = Column(String(36), nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(String(36), ForeignKey("files.id"), nullable=True)
    task_type = Column(String(50), nullable=False)  # summary, ppt, analysis, codegen, translate
    status = Column(String(20), default="pending")  # pending, running, done, failed
    model_used = Column(String(50))
    input_text = Column(String, nullable=True)  # Natural language input text
    result_path = Column(String(500), nullable=True)
    result_text = Column(String, nullable=True)
    error_msg = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    finished_at = Column(DateTime, nullable=True)

from app.models.chat import Conversation, Message
from app.models.user_profile import UserProfile
