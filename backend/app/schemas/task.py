from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TaskCreate(BaseModel):
    task_type: Optional[str] = None
    file_id: Optional[str] = None          # legacy single file
    file_ids: Optional[list[str]] = None   # multi-file support
    input_text: Optional[str] = None
    model: Optional[str] = None
    # Summarize extras
    citation_style: Optional[str] = None   # apa, mla, chicago, gbt7714
    extract_keywords: bool = False
    recommend_related: bool = False
    output_language: Optional[str] = None  # "zh" or "en", output language for summary


class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    model_used: Optional[str] = None
    input_text: Optional[str] = None
    result_text: Optional[str] = None
    result_path: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    # Enhanced fields for summarization
    citations: Optional[dict] = None       # {apa: "...", mla: "...", ...}
    keywords: Optional[list] = None        # [{keyword, score}, ...]
    related_papers: Optional[list] = None  # [{title, authors, doi, ...}, ...]

    model_config = {"from_attributes": True}


class TranslateRequest(BaseModel):
    file_id: Optional[str] = None
    file_ids: Optional[list[str]] = None   # multi-file
    input_text: Optional[str] = None       # direct text translation
    source_lang: str = "en"
    target_lang: str = "zh"
    model: Optional[str] = None


class PPTRequest(BaseModel):
    file_id: Optional[str] = None
    file_ids: Optional[list[str]] = None   # multi-file
    text: Optional[str] = None
    template: str = "minimal"              # deprecated; kept for backward compat
    language: str = "zh"
    style_description: Optional[str] = None  # natural language style description
    custom_template_file_id: Optional[str] = None  # user-uploaded pptx template


class CodeGenRequest(BaseModel):
    prompt: str
    file_id: Optional[str] = None
    file_ids: Optional[list[str]] = None   # multi-file
    execute: bool = False
    model: Optional[str] = None


class AnalysisRequest(BaseModel):
    """Enhanced analysis request with chart type and statistical method selection."""
    file_id: Optional[str] = None
    file_ids: Optional[list[str]] = None   # multi-file support
    input_text: Optional[str] = None       # user's analysis requirements
    model: Optional[str] = None
    chart_types: Optional[list[str]] = None  # bar, line, pie, scatter, heatmap, box
    stat_methods: Optional[list[str]] = None  # descriptive, ttest, anova, regression, chi2, correlation
