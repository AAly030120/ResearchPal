import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.core.config import settings
from app.core.security import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models import File
from app.models.chat import Conversation, Message
from app.schemas.chat import (
    ConversationCreate, ConversationResponse, ConversationDetail,
    MessageResponse, ChatRequest,
)
from app.services.llm_service import llm_service
from app.services.file_parser import extract_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(body: ConversationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model = body.model or current_user.preferred_model
    if model and not llm_service._has_key(model):
        for mdl in llm_service._model_configs:
            if llm_service._has_key(mdl["key"]):
                model = mdl["key"]
                break
    if not model:
        for mdl in llm_service._model_configs:
            if llm_service._has_key(mdl["key"]):
                model = mdl["key"]
                break
        if not model:
            model = settings.DEFAULT_MODEL
    conv = Conversation(user_id=current_user.id, title=body.title, model_used=model)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.updated_at.desc()).all()


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == current_user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg_responses = [MessageResponse.model_validate(m) for m in conv.messages]
    return ConversationDetail(conversation=ConversationResponse.model_validate(conv), messages=msg_responses)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == current_user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"detail": "Conversation deleted"}


@router.post("/send")
async def send_message(body: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model = body.model or current_user.preferred_model
    if model and not llm_service._has_key(model):
        for mdl in llm_service._model_configs:
            if llm_service._has_key(mdl["key"]):
                model = mdl["key"]
                break
    if not model:
        for mdl in llm_service._model_configs:
            if llm_service._has_key(mdl["key"]):
                model = mdl["key"]
                break
        if not model:
            model = settings.DEFAULT_MODEL

    # Find or create conversation
    if body.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == body.conversation_id, Conversation.user_id == current_user.id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = body.message[:50] if len(body.message) > 50 else body.message
        conv = Conversation(user_id=current_user.id, title=title, model_used=model)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Parse attached files if any
    file_context = ""
    attached_file_ids: list[str] = []
    if body.file_ids:
        attached_file_ids = body.file_ids
        for fid in body.file_ids:
            file_record = db.query(File).filter(
                File.id == fid, File.user_id == current_user.id
            ).first()
            if not file_record:
                continue
            try:
                parsed = extract_text(file_record.id, file_record.storage_path, file_record.file_type)
                file_content = parsed.get("text", "")[:30000]
                if file_content:
                    meta_parts = [f"文件名: {file_record.original_name}", f"类型: {file_record.file_type}"]
                    if parsed.get("pages_count"):
                        meta_parts.append(f"页数: {parsed['pages_count']} 页")
                    if parsed.get("slides_count"):
                        meta_parts.append(f"幻灯片: {parsed['slides_count']} 页")
                    if parsed.get("paragraphs_count"):
                        meta_parts.append(f"段落: {parsed['paragraphs_count']}")
                    if parsed.get("tables_count"):
                        meta_parts.append(f"表格: {parsed['tables_count']} 个")
                    if len(file_content) >= 30000:
                        meta_parts.append("⚠️ 文件过长，已截取前 30000 字符")
                    file_context += (
                        f"\n\n[用户上传了文件 {len(attached_file_ids)}/]\n"
                        f"{', '.join(meta_parts)}\n"
                        f"文件内容:\n```\n{file_content}\n```\n"
                    )
            except Exception as e:
                logger.warning(f"Failed to parse file {fid}: {e}")
                file_context += f"\n\n[用户上传了文件: {file_record.original_name}，解析失败: {str(e)}]"

    # Save user message (clean, without file context)
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.message,
        file_id=",".join(attached_file_ids) if attached_file_ids else None,
    )
    db.add(user_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Prepare message history for LLM
    history = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at).all()
    llm_messages = []
    for m in history:
        content = m.content
        # For the current user message, append file context if any
        if m.id == user_msg.id and file_context:
            content = m.content + file_context
        llm_messages.append({"role": m.role, "content": content})

    async def stream_response():
        full_response = ""
        try:
            async for chunk in llm_service.chat_stream(model, llm_messages):
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception as e:
            logger.error(f"Chat error: {e}")
            error_msg = str(e)
            full_response = f"[Error] {error_msg}"
            yield f"data: {json.dumps({'chunk': error_msg, 'error': True})}\n\n"

        # Save assistant message
        assistant_msg = Message(conversation_id=conv.id, role="assistant", content=full_response)
        db.add(assistant_msg)
        conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        yield f"data: {json.dumps({'done': True, 'conversation_id': conv.id})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
