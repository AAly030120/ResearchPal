from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class FileResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    file_type: str
    file_size: int
    uploaded_at: datetime
    version: int = 1
    version_group: Optional[str] = None
    indexed: bool = False
    chunks_count: int = 0

    model_config = {"from_attributes": True}


class ChunkStartRequest(BaseModel):
    filename: str
    file_size: int
    total_chunks: int


class ChunkStartResponse(BaseModel):
    upload_id: str


class ChunkCompleteRequest(BaseModel):
    upload_id: str


class FileVersionInfo(BaseModel):
    id: str
    version: int
    file_size: int
    uploaded_at: datetime
