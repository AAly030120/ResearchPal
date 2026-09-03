import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, func
from sqlalchemy.orm import relationship
from app.models.database import Base

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    preferred_model = Column(String(50), default="gpt-4o-mini")
    language = Column(String(10), default="zh")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    profile = relationship("UserProfile", back_populates="user", uselist=False)
