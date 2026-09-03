"""
User Memory Service — builds a growing profile of the user's style, preferences,
and domain expertise as they interact with ResearchPal.

This makes the app "smarter over time" by injecting contextual hints into LLM prompts.
"""
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models import Task

logger = logging.getLogger(__name__)

# Maximum number of recent task summaries to keep
MAX_RECENT_TASKS = 20


def get_or_create_profile(db: Session, user: User) -> UserProfile:
    """Get existing profile or create a new one."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        profile = UserProfile(
            user_id=user.id,
            preferred_model=user.preferred_model,
            preferred_language=user.language or "zh",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def record_task_completion(
    db: Session,
    user: User,
    task_type: str,
    input_text: Optional[str] = None,
    result_text: Optional[str] = None,
    model_used: Optional[str] = None,
):
    """Record a completed task to build user memory."""
    try:
        profile = get_or_create_profile(db, user)

        # Update counters
        profile.total_tasks = (profile.total_tasks or 0) + 1
        if task_type == "summarize":
            profile.summarizations = (profile.summarizations or 0) + 1
        elif task_type == "ppt":
            profile.ppt_generations = (profile.ppt_generations or 0) + 1
        elif task_type == "analyze":
            profile.analyses = (profile.analyses or 0) + 1
        elif task_type == "codegen":
            profile.code_generations = (profile.code_generations or 0) + 1
        elif task_type == "translate":
            profile.translations = (profile.translations or 0) + 1

        if model_used:
            profile.preferred_model = model_used

        # Update style fingerprint
        _update_style_profile(profile, task_type, input_text, result_text)

        # Update recent context
        _add_recent_context(profile, task_type, input_text)

        db.commit()
    except Exception as e:
        logger.warning(f"Memory update failed (non-critical): {e}")
        db.rollback()


def record_chat_message(db: Session, user: User):
    """Record a chat message for usage tracking."""
    try:
        profile = get_or_create_profile(db, user)
        profile.total_chats = (profile.total_chats or 0) + 1
        db.commit()
    except Exception as e:
        logger.warning(f"Chat memory update failed: {e}")
        db.rollback()


def get_user_context_hint(db: Session, user: User, task_type: str) -> str:
    """Generate a context hint string to inject into LLM prompts.
    
    Returns a short paragraph about the user's style preferences based on history.
    Returns empty string if not enough data.
    """
    try:
        profile = get_or_create_profile(db, user)
        if profile.total_tasks < 3:
            return ""  # Not enough data yet

        style = json.loads(profile.style_profile or "{}")
        hints = []

        # Domain expertise
        domains = style.get("domains", [])
        if domains:
            top_domains = domains[:3] if len(domains) > 3 else domains
            hints.append(f"用户经常处理{', '.join(top_domains)}相关的内容")

        # Formality preference
        formality = style.get("formality", "")
        if formality:
            hints.append(f"用户偏好{formality}风格")

        # Detail level
        detail = style.get("preferred_detail_level", "")
        if detail:
            hints.append(f"回复详细程度偏好: {detail}")

        # Common file types
        file_types = style.get("common_file_types", [])
        if file_types:
            hints.append(f"常用文件类型: {', '.join(file_types[:3])}")

        if not hints:
            return ""

        context = "## 用户画像（基于历史使用）\n" + "\n".join(f"- {h}" for h in hints)

        # Add recent task context
        recent = json.loads(profile.recent_context or "[]")
        if recent:
            recent_str = "\n".join(f"- [{r['type']}] {r['summary'][:100]}" for r in recent[-3:])
            context += f"\n\n## 近期操作\n{recent_str}"

        return context

    except Exception as e:
        logger.warning(f"Context hint generation failed: {e}")
        return ""


def _update_style_profile(profile: UserProfile, task_type: str, input_text: str | None, result_text: str | None):
    """Extract style signals from task interaction."""
    try:
        style = json.loads(profile.style_profile or "{}")

        # Track task types used
        tasks_used = style.get("task_types", {})
        tasks_used[task_type] = tasks_used.get(task_type, 0) + 1
        style["task_types"] = tasks_used

        # Try to extract topics from input_text
        if input_text:
            text_lower = input_text.lower()
            # Simple keyword-based domain detection
            domain_keywords = {
                "机器学习": ["machine learning", "ml", "深度学习", "deep learning", "神经网络", "neural network", "transformer", "gpt", "llm"],
                "数据分析": ["data analysis", "数据分析", "pandas", "statistics", "统计", "可视化", "visualization"],
                "自然语言处理": ["nlp", "自然语言", "文本", "text", "token"],
                "计算机视觉": ["cv", "computer vision", "图像", "image", "视觉"],
                "生物医学": ["医学", "medical", "biology", "生物", "临床", "clinical", "gene", "基因"],
                "金融经济": ["金融", "finance", "经济", "econom", "股票", "stock", "投资"],
                "教育学术": ["论文", "paper", "research", "研究", "学术", "academic", "教育", "education"],
                "编程开发": ["python", "编程", "代码", "code", "开发", "development", "api"],
            }
            for domain, keywords in domain_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        domains = style.get("domains", [])
                        if domain not in domains:
                            domains.append(domain)
                            style["domains"] = domains[-8:]  # Keep last 8
                        break

            # Detect formality from input style
            if any(w in text_lower for w in ["请", "您", "正式", "严谨", "学术"]):
                style["formality"] = "正式学术"
            elif any(w in text_lower for w in ["简单", "快速", "简要", "简短"]):
                style["preferred_detail_level"] = "简洁"
            elif any(w in text_lower for w in ["详细", "全面", "深入", "完整"]):
                style["preferred_detail_level"] = "详细全面"

        # Detect common file types from task type
        file_type_map = {
            "summarize": "pdf",
            "ppt": "pptx",
            "analyze": "csv",
            "codegen": "py",
            "translate": "docx",
        }
        ft = file_type_map.get(task_type)
        if ft:
            common_fts = style.get("common_file_types", [])
            if ft not in common_fts:
                common_fts.append(ft)
                style["common_file_types"] = common_fts[-6:]

        profile.style_profile = json.dumps(style, ensure_ascii=False)
    except Exception:
        pass


def _add_recent_context(profile: UserProfile, task_type: str, input_text: str | None):
    """Add a recent task summary to the context ring buffer."""
    try:
        recent = json.loads(profile.recent_context or "[]")
        summary = (input_text or "")[:200]
        recent.append({"type": task_type, "summary": summary, "at": None})  # time handled by DB

        # Keep only last MAX_RECENT_TASKS
        if len(recent) > MAX_RECENT_TASKS:
            recent = recent[-MAX_RECENT_TASKS:]

        profile.recent_context = json.dumps(recent, ensure_ascii=False)
    except Exception:
        pass
