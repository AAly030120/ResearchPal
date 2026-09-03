"""Settings API - manage API keys and preferences at runtime."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.key_manager import key_manager
from app.models.user import User
from app.models.database import get_db
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


class ApiKeyUpdate(BaseModel):
    key_env: str  # e.g. "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY"
    value: str


class ApiKeyStatus(BaseModel):
    key_env: str
    configured: bool
    masked: str
    label: str


@router.get("/keys", response_model=list[ApiKeyStatus])
async def list_key_status(current_user: User = Depends(get_current_user)):
    """List all API key statuses (masked)."""
    status = key_manager.get_all_status()
    labels = {
        "OPENAI_API_KEY": "OpenAI (GPT-4o / GPT-4o Mini)",
        "DEEPSEEK_API_KEY": "DeepSeek (V3 / V4 Flash)",
        "GLM_API_KEY": "智谱 (GLM-4 Flash / GLM-5.2)",
        "QWEN_API_KEY": "通义千问 (Qwen3.5 系列)",
    }
    return [
        ApiKeyStatus(
            key_env=k,
            configured=v["configured"],
            masked=v["masked"],
            label=labels.get(k, k),
        )
        for k, v in status.items()
    ]


@router.put("/keys")
async def set_api_key(body: ApiKeyUpdate, current_user: User = Depends(get_current_user)):
    """Set an API key at runtime."""
    allowed = {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY"}
    if body.key_env not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown key: {body.key_env}. Allowed: {allowed}")
    key_manager.set(body.key_env, body.value)
    # Clear cached clients so they re-read keys
    llm_service._clients.clear()
    logger.info(f"API key updated for {body.key_env} by user {current_user.id}")
    return {"detail": "API key updated successfully", "key_env": body.key_env}


@router.delete("/keys/{key_env}")
async def delete_api_key(key_env: str, current_user: User = Depends(get_current_user)):
    """Remove an API key."""
    allowed = {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY"}
    if key_env not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key_env}")
    key_manager.set(key_env, "")
    llm_service._clients.clear()
    return {"detail": "API key removed", "key_env": key_env}


@router.get("/models")
async def list_models(current_user: User = Depends(get_current_user)):
    """List available AI models and their configuration status."""
    models = llm_service.get_available_models()
    has_any_key = any(m["available"] for m in models)
    return {
        "models": models,
        "demo_mode": not has_any_key,
        "message": (
            "At least one API key is configured. AI tools are ready."
            if has_any_key
            else "No API keys configured. Running in demo mode. Configure keys in Settings to enable AI features."
        ),
    }
