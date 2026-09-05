from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MessageCreate(BaseModel):
    role: str
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    file_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: str = "New Chat"
    model: Optional[str] = "gpt-4o-mini"


class ConversationResponse(BaseModel):
    id: str
    title: str
    model_used: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    file_ids: Optional[list[str]] = None  # Support multiple file uploads
    model: Optional[str] = None
    use_rag: Optional[bool] = True  # Enable RAG retrieval augmentation over indexed documents
