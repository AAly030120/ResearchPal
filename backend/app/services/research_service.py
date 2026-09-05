"""
Deep-research agent (GraphRAG + RAG powered).

Given a topic, it:
  1. Plans 3-4 sub-questions (outline) via the LLM.
  2. For each sub-question, retrieves grounded context (vector RAG + knowledge
     graph) and streams a synthesized section.
  3. Appends a references section and emits the full report.

Yields SSE-style dict events: {"stage":"plan"|"chunk"|"refs"|"done", ...}.
"""
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional

from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.kg_store import get_graph, retrieve_context as kg_retrieve

logger = logging.getLogger(__name__)


def _parse_plan(text: str) -> List[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out: List[str] = []
    for l in lines:
        m = re.match(r"^\s*(\d+)[.、)]\s*(.+)", l)
        if m:
            out.append(m.group(2).strip())
        elif len(out) < 4 and 2 < len(l) < 80:
            out.append(l)
    return out[:4] if out else [text.strip()]


async def _retrieve(user_id: str, query: str, file_ids: Optional[List[str]], has_docs: bool):
    ctx_parts: List[str] = []
    sources: List[dict] = []
    if has_docs:
        hits = rag_service.retrieve(user_id, query, file_ids=file_ids)
        if hits:
            c, s = rag_service.format_context(hits)
            ctx_parts.append(c)
            sources.extend(s)
    try:
        if get_graph(user_id).number_of_nodes() > 0:
            kg_ctx, kg_src = kg_retrieve(query, user_id, file_ids=file_ids)
            if kg_ctx:
                ctx_parts.append(kg_ctx)
                sources.extend(kg_src)
    except Exception as e:  # pragma: no cover
        logger.warning("research KG retrieve failed: %s", e)
    return "\n\n".join(ctx_parts), sources


async def research_stream(
    topic: str,
    user_id: str,
    model: str,
    file_ids: Optional[List[str]] = None,
) -> AsyncGenerator[Dict, None]:
    has_docs = rag_service.has_documents(user_id)
    all_sources: List[dict] = []
    full: List[str] = [f"# {topic}\n\n"]

    # 1) Plan outline
    plan_prompt = (
        f"为研究主题『{topic}』生成一个包含 3-4 个研究子方向的大纲。"
        "每行一个，用 '1. ' 这样的编号开头，只列子方向标题，不要解释。"
    )
    try:
        plan = await llm_service.chat_complete(
            model, [{"role": "user", "content": plan_prompt}], temperature=0.3, max_tokens=400
        )
    except Exception as e:
        logger.warning("research plan failed: %s", e)
        plan = topic
    subquestions = _parse_plan(plan)
    yield {"stage": "plan", "text": plan}
    full.append("## 研究大纲\n")
    for i, sq in enumerate(subquestions, 1):
        full.append(f"{i}. {sq}\n")

    # 2) Per sub-question synthesis (streamed)
    for i, sq in enumerate(subquestions, 1):
        ctx, srcs = await _retrieve(user_id, sq, file_ids, has_docs)
        all_sources.extend(srcs)
        header = f"\n\n## {i}. {sq}\n"
        yield {"chunk": header}
        full.append(header)

        if not ctx:
            note = "（未检索到相关资料，以下为基于模型通用知识的概述，请自行核实。）\n"
            yield {"chunk": note}
            full.append(note)
            section_prompt = f"请就『{sq}』撰写一段严谨的中文概述（约 200 字）。"
        else:
            section_prompt = (
                f"你是严谨的科研助手。基于下方【资料】就『{sq}』撰写一段论述（中文，"
                f"使用 [来源: 文件名 #片段N] 或 [来源: 实体名] 标注引用，约 250 字）：\n\n{ctx}"
            )
        section_text = ""
        try:
            async for chunk in llm_service.chat_stream(
                model, [{"role": "user", "content": section_prompt}], temperature=0.3, max_tokens=1200
            ):
                section_text += chunk
                yield {"chunk": chunk}
        except Exception as e:
            logger.warning("research section stream failed: %s", e)
            section_text = f"（生成失败：{e}）"
            yield {"chunk": section_text}
        full.append(section_text)

    # 3) References
    refs = "\n\n## 参考来源\n"
    seen = set()
    for s in all_sources:
        key = (s.get("file"), s.get("chunk"), s.get("page"))
        if key in seen:
            continue
        seen.add(key)
        loc = f" 第{s['page']}页" if s.get("page") else ""
        refs += f"- {s.get('file', '资料')}{loc} · #{s.get('chunk', '?')}\n"
    if len(seen) == 0:
        refs += "- （本次未使用已上传文献）\n"
    full.append(refs)
    yield {"stage": "refs", "text": refs}
    yield {
        "done": True,
        "content": "".join(full),
        "sources": all_sources,
        "retrieved_count": len(all_sources),
    }
