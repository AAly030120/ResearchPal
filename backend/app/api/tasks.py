import os
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models import File, Task
from app.schemas.task import (
    TaskResponse,
    TaskCreate,
    TranslateRequest,
    PPTRequest,
    CodeGenRequest,
    AnalysisRequest,
)
from app.services.llm_service import llm_service
from app.services import demo_service
from app.services.file_parser import extract_text
from app.services.ppt_service import (
    generate_pptx_from_outline,
    OUTLINE_SYSTEM_PROMPT,
    SVG_SYSTEM_PROMPT,
)
from app.services.sandbox import run_python
from app.services.translation_service import translate_text, translate_file
from app.services.memory_service import record_task_completion, get_user_context_hint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── helpers ──────────────────────────────────────────────────────────

def _get_model(user: User, request_model: str = None) -> str:
    """Smart model selection: prefer user choice, then first available model with API key."""
    selected = request_model or user.preferred_model
    if selected:
        cfg = llm_service._get_config(selected)
        if llm_service._has_key(selected):
            return selected
    for mdl in llm_service._model_configs:
        if llm_service._has_key(mdl["key"]):
            logger.info(f"Auto-selected model {mdl['key']} (has API key)")
            return mdl["key"]
    return settings.DEFAULT_MODEL


def _check_demo_response(response_text: str, model: str) -> bool:
    demo_markers = [
        "ResearchPal AI 助手（Demo 模式）",
        "Demo 模式",
        "演示模式",
        "API Key，我运行在演示模式",
    ]
    return any(marker in response_text for marker in demo_markers)


def _create_task(
    db: Session, user_id: str, task_type: str, file_id: str = None,
    input_text: str = None, model: str = None,
) -> Task:
    task = Task(
        user_id=user_id,
        task_type=task_type,
        file_id=file_id,
        input_text=input_text,
        model_used=model,
        status="running",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _fail_task(db: Session, task: Task, error: str):
    task.status = "failed"
    task.error_msg = str(error)
    task.finished_at = datetime.now(timezone.utc)
    db.commit()


def _done_task(db: Session, task: Task, result_text: str = None, result_path: str = None,
               record_memory: bool = True):
    task.status = "done"
    task.result_text = result_text
    task.result_path = result_path
    task.finished_at = datetime.now(timezone.utc)
    db.commit()
    # Memory recording is handled at endpoint level with proper user object


def _resolve_files(
    file_id: str | None,
    file_ids: list[str] | None,
    user_id: str,
    db: Session,
) -> list[File]:
    """Resolve file references from both legacy file_id and new file_ids."""
    all_ids = []
    if file_id:
        all_ids.append(file_id)
    if file_ids:
        all_ids.extend(file_ids)
    if not all_ids:
        return []
    records = db.query(File).filter(
        File.id.in_(all_ids), File.user_id == user_id
    ).all()
    return records


def _parse_files_context(file_records: list, max_chars: int = 30000) -> str:
    """Parse all files and return combined text context with metadata."""
    parts = []
    for f in file_records:
        try:
            parsed = extract_text(f.id, f.storage_path, f.file_type)
            content = parsed.get("text", "")
            if not content:
                continue
            meta = [f"📄 {f.original_name} ({f.file_type})"]
            if parsed.get("pages_count"):
                meta.append(f"{parsed['pages_count']}页")
            if parsed.get("slides_count"):
                meta.append(f"{parsed['slides_count']}幻灯片")
            if parsed.get("paragraphs_count"):
                meta.append(f"{parsed['paragraphs_count']}段落")
            if parsed.get("tables_count"):
                meta.append(f"{parsed['tables_count']}表格")
            header = f"[{', '.join(meta)}]\n"
            truncated = content[:max_chars // max(len(file_records), 1)]
            if len(content) > len(truncated):
                truncated += "\n... [内容已截断]"
            parts.append(header + truncated)
        except Exception as e:
            logger.warning(f"Failed to parse {f.original_name}: {e}")
            parts.append(f"[文件 {f.original_name} 解析失败: {e}]")
    return "\n\n---\n\n".join(parts)


def _safe_json_dumps(obj, **kwargs):
    """json.dumps that handles Timestamp, datetime, etc."""
    import numpy as np

    class SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if hasattr(o, 'isoformat'):
                return o.isoformat()
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, (np.ndarray,)):
                return o.tolist()
            return str(o)

    return json.dumps(obj, cls=SafeEncoder, ensure_ascii=False, **kwargs)


# ── Summarize ─────────────────────────────────────────────────────────

@router.post("/summarize")
async def summarize_document(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = _get_model(current_user, body.model)
    task = _create_task(
        db, current_user.id, "summarize",
        file_id=body.file_id, input_text=body.input_text, model=model,
    )

    try:
        file_records = _resolve_files(body.file_id, body.file_ids, current_user.id, db)
        file_text = _parse_files_context(file_records) if file_records else ""
        text = (body.input_text or "") + ("\n\n" + file_text if file_text else "")

        if not text.strip():
            raise ValueError("请上传文件或输入文本内容")

        # ── Demo mode: no API key configured ──
        if not llm_service.has_any_key():
            summary, citations, keywords, related = demo_service.demo_summarize(text)
            _done_task(db, task, result_text=summary)
            record_task_completion(db, current_user, "summarize", body.input_text, summary, model)
            db.refresh(task)
            task_dict = {c.name: getattr(task, c.name) for c in task.__table__.columns}
            task_dict["citations"] = citations
            task_dict["keywords"] = keywords
            task_dict["related_papers"] = related
            return TaskResponse(**task_dict)

        max_chunk = 8000
        chunks = [text[i:i+max_chunk] for i in range(0, len(text), max_chunk)]
        summaries = []

        # Enhanced system prompt that also extracts metadata
        output_lang = body.output_language or "auto"
        lang_instruction = ""
        if output_lang == "zh":
            lang_instruction = "YOUR RESPONSE MUST BE IN CHINESE (简体中文). Translate the summary to Chinese regardless of the input language. "
        elif output_lang == "en":
            lang_instruction = "YOUR RESPONSE MUST BE IN ENGLISH. Translate the summary to English regardless of the input language. "
        
        system_prompt = (
            "You are an expert academic summarizer. "
            + lang_instruction +
            "Generate a concise, well-structured summary. "
            "Focus on key findings, methodology, and conclusions. "
            "Format your response in Markdown with clear sections."
            "\n\nAfter the summary, add a section '## 文献元数据' that extracts:"
            "\n- 作者 (Authors)"
            "\n- 标题 (Title)"
            "\n- 期刊/会议 (Journal/Conference)"
            "\n- 发表年份 (Year)"
            "\n- DOI (if present)"
            "\n- 卷/期/页码 (Volume/Issue/Pages)"
        )

        for i, chunk in enumerate(chunks):
            prompt = f"Summarize the following text:\n\n{chunk}"
            if len(chunks) > 1:
                prompt = f"Part {i+1}/{len(chunks)}. {prompt}"
            result = await llm_service.chat_complete(
                model, [{"role": "user", "content": prompt}], system_prompt,
            )
            summaries.append(result)

        full_summary = "\n\n".join(summaries)

        # ── Post-processing: Citation, Keywords, Related Papers ─────────
        citations = None
        keywords = None
        related_papers = None

        # Extract metadata from original text only (not LLM output) for citation
        from app.services.citation_service import (
            extract_metadata_from_text, format_citations_batch,
        )
        meta = extract_metadata_from_text(text[:5000])
        if body.citation_style:
            # Single style requested
            single = format_citations_batch(meta)
            citations = {body.citation_style: single.get(body.citation_style, "")}
        else:
            # Return all formats by default
            citations = format_citations_batch(meta)

        # Keyword extraction
        if body.extract_keywords:
            from app.services.keyword_service import extract_keywords as kw_extract
            keywords = kw_extract(text, top_n=15)

        # Similar paper recommendation
        if body.recommend_related and keywords:
            from app.services.keyword_service import recommend_similar_papers_sync
            related_papers = recommend_similar_papers_sync(keywords, num_results=5)

        _done_task(db, task, result_text=full_summary)
        record_task_completion(db, current_user, "summarize", body.input_text, full_summary, model)
        db.refresh(task)

        # Build response with all enhanced fields
        task_dict = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        task_dict["citations"] = citations
        task_dict["keywords"] = keywords
        task_dict["related_papers"] = related_papers
        return TaskResponse(**task_dict)

    except Exception as e:
        logger.error(f"Summarize error: {e}")
        _fail_task(db, task, str(e))
        db.refresh(task)
        return TaskResponse.model_validate(task)


# ── PPT ────────────────────────────────────────────────────────────────


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences from LLM JSON output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text.strip()


@router.post("/ppt", response_model=TaskResponse)
async def generate_ppt(
    body: PPTRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = _get_model(current_user)
    task = _create_task(
        db, current_user.id, "ppt",
        file_id=body.file_id, input_text=body.text, model=model,
    )

    try:
        # ── 1. Collect source text ─────────────────────────────────────
        file_records = _resolve_files(body.file_id, body.file_ids, current_user.id, db)
        file_text = _parse_files_context(file_records) if file_records else ""
        text = (body.text or "") + ("\n\n" + file_text if file_text else "")

        if not text.strip():
            raise ValueError("请上传文件或输入 PPT 内容")

        # ── Demo mode: no API key configured ──
        if not llm_service.has_any_key():
            output_path, _outline = demo_service.demo_ppt()
            _done_task(db, task, result_path=output_path)
            record_task_completion(db, current_user, "ppt", body.text, None, model)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        # ── 2. Generate structured outline via LLM ─────────────────────
        style_desc = (body.style_description or "").strip() or "专业学术风格，蓝白配色，清晰整洁"
        language = getattr(body, "language", "zh")

        outline_system = OUTLINE_SYSTEM_PROMPT.format(
            language=language,
            style_description=style_desc,
        )

        outline_text = await llm_service.chat_complete(
            model,
            [{"role": "user", "content": f"请根据以下内容制作PPT大纲：\n\n{text[:12000]}"}],
            outline_system,
            temperature=0.6,
        )

        if _check_demo_response(outline_text, model):
            raise ValueError(
                '当前处于 Demo 模式，无法生成 PPT。请在「设置」页面配置至少一个 AI 模型的 API Key。\n'
                '支持的模型：OpenAI GPT-4o / DeepSeek V3 / 智谱 GLM-4 Flash'
            )

        try:
            outline = json.loads(_strip_json_fences(outline_text))
        except json.JSONDecodeError:
            raise ValueError("AI 生成的 PPT 大纲格式无效，请重试")

        design = outline.get("design", {})
        if not design:
            design = {
                "bg": "#FFFFFF", "primary": "#1A56E8", "accent": "#F59E0B",
                "text": "#1F2937", "text_light": "#6B7280",
                "font_title": "Arial", "font_body": "Arial", "dark_mode": False,
            }

        # ── 3. Generate PPTX using SVG pipeline + ppt-master ──────────
        output_path = generate_pptx_from_outline(outline, design)

        _done_task(db, task, result_path=output_path)
        record_task_completion(db, current_user, "ppt", body.text, None, model)
        db.refresh(task)
        return TaskResponse.model_validate(task)

    except Exception as e:
        logger.error(f"PPT generation error: {e}", exc_info=True)
        _fail_task(db, task, str(e))
        db.refresh(task)
        return TaskResponse.model_validate(task)


# ── Data Analysis ─────────────────────────────────────────────────────

# ── Chart type & Statistics guidance ───────────────────────────────────

CHART_GUIDANCE = {
    "bar": "Generate BAR CHARTS (matplotlib bar/barh) to compare categorical values.",
    "line": "Generate LINE CHARTS (matplotlib plot) to show trends over time or sequences.",
    "pie": "Generate PIE CHARTS (matplotlib pie) to show proportions and percentages.",
    "scatter": "Generate SCATTER PLOTS (matplotlib scatter) to show relationships between two numeric variables.",
    "heatmap": "Generate HEATMAPS (seaborn heatmap) to visualize correlation matrices or data density.",
    "box": "Generate BOX PLOTS (matplotlib boxplot/seaborn boxplot) to show data distribution and outliers.",
}

STAT_GUIDANCE = {
    "descriptive": "Compute DESCRIPTIVE STATISTICS: mean, median, std, min, max, quartiles, skewness, kurtosis. Use df.describe() and add custom calculations.",
    "ttest": "Perform T-TEST: compare means between two groups. Use scipy.stats.ttest_ind (independent) or ttest_rel (paired). Include p-value interpretation.",
    "anova": "Perform ONE-WAY ANOVA: compare means across 3+ groups. Use scipy.stats.f_oneway. Include F-statistic and p-value.",
    "regression": "Perform LINEAR REGRESSION: model relationship between variables. Use scipy.stats.linregress or sklearn.linear_model. Include R-squared, coefficients, and residual plots.",
    "chi2": "Perform CHI-SQUARE TEST: test independence between categorical variables. Use scipy.stats.chi2_contingency. Include chi2 statistic and p-value.",
    "correlation": "Compute CORRELATION ANALYSIS: Pearson/Spearman correlation matrix. Use df.corr() and seaborn.heatmap. Highlight strongest correlations.",
}

@router.post("/analyze", response_model=TaskResponse)
async def analyze_data(
    body: AnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = _get_model(current_user, body.model)
    task = _create_task(
        db, current_user.id, "analyze",
        file_id=body.file_id, input_text=body.input_text, model=model,
    )

    try:
        file_records = _resolve_files(body.file_id, body.file_ids, current_user.id, db)
        if not file_records:
            raise ValueError("请上传数据文件（支持 CSV、Excel、PDF、Word 等所有格式）")

        # ── Demo mode: no API key configured ──
        if not llm_service.has_any_key():
            data_file = next(
                (f for f in file_records if f.file_type in ("csv", "xlsx", "xls")), None
            )
            if data_file is None:
                ctx = _parse_files_context(file_records) if file_records else (body.input_text or "")
                summary = demo_service.demo_analyze(file_context=ctx)
            else:
                summary = demo_service.demo_analyze(data_file=data_file)
            _done_task(db, task, result_text=summary)
            record_task_completion(db, current_user, "analyze", body.input_text, summary, model)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        # Find the primary data file (CSV/Excel) and secondary context files
        data_file = None
        context_files = []
        for f in file_records:
            if f.file_type in ("csv", "xlsx", "xls") and data_file is None:
                data_file = f
            else:
                context_files.append(f)

        if not data_file:
            # No structured data file — treat ALL files as context + user instructions
            file_context = _parse_files_context(file_records)
            prompt_text = (body.input_text or "") + "\n\n文件内容：\n" + file_context
            system_prompt = (
                "You are a data scientist. The user has provided files and requests analysis. "
                "If files contain tabular data, extract it and generate Python code to analyze it. "
                "Otherwise, provide a thorough analysis of the file contents. "
                "Generate clean, well-commented Python code for any data processing. "
                "Output Python code with markdown analysis, like:\n"
                "```python\n...\n```\n\nAnalysis: ..."
            )
            result = await llm_service.chat_complete(
                model, [{"role": "user", "content": prompt_text[:8000]}], system_prompt,
                temperature=0.3,
            )
            if _check_demo_response(result, model):
                raise ValueError(
                    '当前处于 Demo 模式，无法执行数据分析。请在「设置」页面配置至少一个 AI 模型的 API Key。'
                )
            _done_task(db, task, result_text=result)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        # We have a structured data file — parse it and generate analysis code
        parsed = extract_text(data_file.id, data_file.storage_path, data_file.file_type)

        # Build preview safely (handle Timestamps)
        preview_data = parsed.get("preview", parsed.get("dataframes", {}))
        preview_json = _safe_json_dumps(preview_data, indent=2)[:4000]

        columns_info = parsed.get("columns", [])
        if not columns_info and isinstance(preview_data, dict):
            for sheet_name, sheet_data in preview_data.items():
                if isinstance(sheet_data, dict) and "columns" in sheet_data:
                    columns_info = sheet_data["columns"]
                    break

        # Build context from non-data files
        context_text = ""
        if context_files:
            context_text = _parse_files_context(context_files, max_chars=4000)

        # User instructions — incorporate chart types and stat methods
        user_instruction = body.input_text or "对数据集进行全面分析，包括统计特征、数据分布、相关性分析和异常值检测"

        # Inject chart type guidance
        if body.chart_types and len(body.chart_types) > 0:
            chart_instructions = "\n".join(
                CHART_GUIDANCE.get(ct, "") for ct in body.chart_types if ct in CHART_GUIDANCE
            )
            if chart_instructions:
                user_instruction += f"\n\n图表要求：\n{chart_instructions}\n请为每种图表类型至少生成一张图表。"

        # Inject statistical method guidance
        if body.stat_methods and len(body.stat_methods) > 0:
            stat_instructions = "\n".join(
                f"- {STAT_GUIDANCE.get(sm, sm)}" for sm in body.stat_methods if sm in STAT_GUIDANCE
            )
            if stat_instructions:
                user_instruction += f"\n\n统计方法要求：\n{stat_instructions}"

        system_prompt = (
            "You are a data scientist. Generate Python code to analyze the provided data. "
            "The code must:\n"
            "1. Use _DATA (a pre-loaded pandas DataFrame) for analysis\n"
            "2. Create matplotlib/seaborn charts with plt.show() to display them\n"
            "3. Print key findings and statistics in Chinese\n"
            "4. Use scipy.stats for statistical tests when needed\n"
            "5. Be complete and runnable\n"
            "6. Add plt.figure(figsize=(10,6)) before each chart for better sizing\n"
            "7. Set Chinese font for matplotlib: plt.rcParams['font.sans-serif']=['SimHei','DejaVu Sans']\n"
            "Output ONLY Python code, no explanations or markdown fences."
        )

        prompt = (
            f"数据集列: {columns_info}\n"
            f"数据预览:\n{preview_json}\n"
        )
        if context_text:
            prompt += f"\n附加参考文件内容:\n{context_text}\n"
        prompt += f"\n分析需求: {user_instruction}"

        code = await llm_service.chat_complete(
            model, [{"role": "user", "content": prompt}], system_prompt,
            temperature=0.2,
        )

        if _check_demo_response(code, model):
            raise ValueError(
                '当前处于 Demo 模式，无法执行数据分析。请在「设置」页面配置至少一个 AI 模型的 API Key。\n'
                '支持的模型：OpenAI GPT-4o / DeepSeek V3 / 智谱 GLM-4 Flash'
            )

        # Clean code output
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        # Execute in sandbox
        result = run_python(code, data_path=data_file.storage_path)

        summary = f"## 数据分析结果\n\n"
        if result["stdout"]:
            summary += f"**输出：**\n```\n{result['stdout'][:2000]}\n```\n\n"
        if result["error"]:
            summary += f"**错误：** {result['error']}\n\n"
        if result["charts"]:
            summary += f"**生成图表：** {len(result['charts'])} 张\n"
        summary += f"\n**分析代码：**\n```python\n{code[:2000]}\n```"

        result_data = {
            "summary": summary,
            "charts": result["charts"],
            "stdout": result["stdout"],
            "error": result.get("error"),
            "code": code,
        }

        _done_task(db, task, result_text=_safe_json_dumps(result_data))
        record_task_completion(db, current_user, "analyze", body.input_text, summary, model)
        db.refresh(task)
        return TaskResponse.model_validate(task)

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        _fail_task(db, task, str(e))
        db.refresh(task)
        return TaskResponse.model_validate(task)


# ── Code Generation ───────────────────────────────────────────────────

@router.post("/codegen", response_model=TaskResponse)
async def generate_code(
    body: CodeGenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = _get_model(current_user, body.model)
    task = _create_task(
        db, current_user.id, "codegen",
        file_id=body.file_id, input_text=body.prompt, model=model,
    )

    try:
        # Gather context from all files
        file_records = _resolve_files(body.file_id, body.file_ids, current_user.id, db)

        # ── Demo mode: no API key configured ──
        if not llm_service.has_any_key():
            result_text = demo_service.demo_codegen(body.prompt, body.execute)
            _done_task(db, task, result_text=result_text)
            record_task_completion(db, current_user, "codegen", body.prompt, result_text, model)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        file_context = ""
        data_path = None
        if file_records:
            data_files = [f for f in file_records if f.file_type in ("csv", "xlsx", "xls")]
            docs = [f for f in file_records if f.file_type not in ("csv", "xlsx", "xls")]

            if data_files:
                parsed = extract_text(data_files[0].id, data_files[0].storage_path, data_files[0].file_type)
                file_context += f"数据分析文件: {data_files[0].original_name}\n列: {parsed.get('columns', [])}\n\n"
                data_path = data_files[0].storage_path

            if docs:
                file_context += _parse_files_context(docs, max_chars=8000)

        system_prompt = (
            "You are an expert programmer. Generate clean, well-commented Python code. "
            "Output ONLY the code, no explanations or markdown fences. "
            "The code should be complete and runnable."
        )

        prompt = body.prompt
        if file_context:
            prompt = f"{file_context}\n\n任务: {prompt}"

        code = await llm_service.chat_complete(
            model, [{"role": "user", "content": prompt}], system_prompt,
            temperature=0.2, max_tokens=4096,
        )

        if _check_demo_response(code, model):
            raise ValueError(
                '当前处于 Demo 模式，无法生成代码。请在「设置」页面配置至少一个 AI 模型的 API Key。\n'
                '支持的模型：OpenAI GPT-4o / DeepSeek V3 / 智谱 GLM-4 Flash'
            )

        # Clean code
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        result_text = f"```python\n{code}\n```"
        if body.execute:
            sandbox_result = run_python(code, data_path=data_path)
            result_text += (
                f"\n\n### 执行结果\n"
                f"**输出：**\n```\n{sandbox_result['stdout'][:2000]}\n```\n"
            )
            if sandbox_result["stderr"]:
                result_text += f"**错误输出：**\n```\n{sandbox_result['stderr'][:2000]}\n```\n"
            if sandbox_result["error"]:
                result_text += f"**异常：** {sandbox_result['error']}\n"
            if sandbox_result["charts"]:
                result_text += f"**图表：** {len(sandbox_result['charts'])} 张已生成\n"

        _done_task(db, task, result_text=result_text)
        record_task_completion(db, current_user, "codegen", body.prompt, result_text, model)
        db.refresh(task)
        return TaskResponse.model_validate(task)

    except Exception as e:
        logger.error(f"Code generation error: {e}")
        _fail_task(db, task, str(e))
        db.refresh(task)
        return TaskResponse.model_validate(task)


# ── Translation ───────────────────────────────────────────────────────

@router.post("/translate", response_model=TaskResponse)
async def translate_endpoint(
    body: TranslateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = _get_model(current_user, body.model)
    task = _create_task(
        db, current_user.id, "translate",
        file_id=body.file_id, model=model,
    )

    try:
        file_records = _resolve_files(body.file_id, body.file_ids, current_user.id, db)

        # ── Demo mode: no API key configured ──
        if not llm_service.has_any_key():
            if body.input_text and not file_records:
                result = demo_service.demo_translate(body.input_text, body.source_lang, body.target_lang)
                _done_task(db, task, result_text=result)
            elif file_records:
                results = []
                for f in file_records:
                    try:
                        parsed = extract_text(f.id, f.storage_path, f.file_type)
                        t = parsed.get("text", "")
                        results.append(
                            f"## {f.original_name}\n\n"
                            f"{demo_service.demo_translate(t[:3000], body.source_lang, body.target_lang)}"
                        )
                    except Exception as e:
                        results.append(f"## {f.original_name}\n\n[解析失败: {e}]")
                _done_task(db, task, result_text="\n\n---\n\n".join(results))
            else:
                raise ValueError("请上传文件或输入文本")
            record_task_completion(db, current_user, "translate", None, None, model)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        if body.input_text and not file_records:
            # Direct text translation
            result = await translate_text(
                body.input_text, body.source_lang, body.target_lang, model
            )
            _done_task(db, task, result_text=result)
            db.refresh(task)
            return TaskResponse.model_validate(task)

        if not file_records:
            raise ValueError("请上传文件或输入文本")

        if len(file_records) == 1:
            # Single file translation
            f = file_records[0]
            try:
                output_path = await translate_file(
                    f.id, f.storage_path, f.file_type,
                    body.source_lang, body.target_lang, model,
                )
                _done_task(db, task, result_path=output_path)
                record_task_completion(db, current_user, "translate", None, None, model)
            except Exception:
                # Fall back to text output if file translation fails
                parsed = extract_text(f.id, f.storage_path, f.file_type)
                text = parsed.get("text", "")
                result = await translate_text(text, body.source_lang, body.target_lang, model)
                _done_task(db, task, result_text=result)
                record_task_completion(db, current_user, "translate", text[:200], result, model)
                record_task_completion(db, current_user, "translate", body.input_text, result, model)
        else:
            # Multiple files — translate each and show results as text
            results = []
            for f in file_records:
                try:
                    parsed = extract_text(f.id, f.storage_path, f.file_type)
                    text = parsed.get("text", "")
                    if text.strip():
                        translated = await translate_text(
                            text[:5000], body.source_lang, body.target_lang, model
                        )
                        results.append(f"## {f.original_name}\n\n{translated}")
                except Exception as e:
                    results.append(f"## {f.original_name}\n\n[翻译失败: {e}]")
            _done_task(db, task, result_text="\n\n---\n\n".join(results))
            record_task_completion(db, current_user, "translate", None, None, model)

        db.refresh(task)
        return TaskResponse.model_validate(task)

    except Exception as e:
        logger.error(f"Translation error: {e}")
        _fail_task(db, task, str(e))
        db.refresh(task)
        return TaskResponse.model_validate(task)


# ── CRUD ──────────────────────────────────────────────────────────────

@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = db.query(Task).filter(Task.user_id == current_user.id).order_by(Task.created_at.desc()).all()
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"detail": "Task deleted"}
