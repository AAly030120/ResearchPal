"""Demo service — produces realistic, runnable results without any LLM API key.

When a fresh clone has no API keys configured, ResearchPal still works end-to-end
so reviewers can click through every feature. Each handler mirrors the shape of
the real (LLM-powered) output so the frontend renders identically.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings
from app.services.ppt_service import generate_pptx_from_outline
from app.services.sandbox import run_python

logger = logging.getLogger(__name__)

# Sample outline used by the demo PPT generator (also renders a real .pptx).
DEMO_PPT_OUTLINE = {
    "title": "ResearchPal 产品演示",
    "subtitle": "AI 驱动的科研助手 · Demo 模式",
    "design": {
        "bg": "#FFFFFF", "primary": "#1A56E8", "accent": "#F59E0B",
        "text": "#1F2937", "text_light": "#6B7280",
        "font_title": "Arial", "font_body": "Arial", "dark_mode": False,
    },
    "slides": [
        {
            "title": "为什么做科研助手",
            "layout": "bullets",
            "bullets": ["文献太长，提炼核心耗时长", "数据分析要写代码，门槛高",
                        "PPT 从零制作费精力", "英文文献阅读有障碍"],
            "notes": "开场说明目标用户的真实痛点。",
        },
        {
            "title": "核心能力",
            "layout": "two_col",
            "bullets": ["文献总结与亮点提炼", "数据分析与图表生成",
                        "自然语言一键生成 PPT", "文件翻译 / 代码生成"],
            "notes": "左右分栏介绍产品功能矩阵。",
        },
        {
            "title": "关键指标",
            "layout": "stats",
            "bullets": ["-37% 端到端耗时", "+4.2 ROUGE-L",
                        "6 种 PPT 布局", "3+ 模型路由"],
            "notes": "用数据说话，体现产品的可量化价值。",
        },
        {
            "title": "技术路线",
            "layout": "timeline",
            "bullets": ["需求解析", "任务调度", "LLM 生成", "沙箱执行", "结果渲染"],
            "notes": "用时间线展示端到端流程。",
        },
        {
            "title": "我们的愿景",
            "layout": "quote",
            "bullets": ["让每一个研究者都把时间花在思考上，而不是重复劳动。", ""],
            "notes": "收尾金句，呼应产品使命。",
        },
    ],
}

DEMO_SUMMARY = """# 示例文献摘要（Demo 模式）

> 当前未配置任何 AI 模型的 API Key，以下为 **演示数据**，仅用于展示界面与流程。

## 核心摘要
本文提出了一种面向科研场景的多智能体协作框架，将文献阅读、数据分析与报告撰写拆解为可并行执行的子任务，并通过统一的记忆模块在任务间传递上下文。在三个公开数据集上的实验表明，该框架在摘要质量（ROUGE-L +4.2）与端到端耗时（−37%）上均优于单智能体基线。

## 关键贡献
- 提出任务级记忆共享机制，降低跨步骤的上下文丢失
- 设计了可按负载动态伸缩的子智能体调度器
- 在保持质量的同时显著缩短科研流水线耗时

## 研究方法
采用 Map-Reduce 摘要策略，先分块提取要点再全局综合；数据分析阶段使用隔离沙箱执行生成的 pandas 代码。

## 主要结论
多智能体协作在长文档科研任务中具有明显优势，且成本可控。

---
## 文献元数据
- 作者：Demo Author et al.
- 标题：A Multi-Agent Framework for Research Workflow Automation
- 期刊/会议：DemoConf 2026
- 发表年份：2026
- DOI：10.xxxx/demo.2026.0001
"""


def demo_summarize(text: str) -> tuple[str, dict, list, Optional[list]]:
    """Return (summary_markdown, citations, keywords, related_papers)."""
    from app.services.citation_service import (
        extract_metadata_from_text, format_citations_batch,
    )

    meta = extract_metadata_from_text((text or "")[:5000])
    citations = format_citations_batch(meta)
    try:
        from app.services.keyword_service import extract_keywords as kw_extract
        keywords = kw_extract(text or "", top_n=15) if text else [
            "大语言模型", "科研自动化", "多智能体", "文本摘要", "数据分析",
        ]
    except Exception:
        # keyword extraction needs optional deps (jieba); don't break demo mode
        keywords = ["大语言模型", "科研自动化", "多智能体", "文本摘要", "数据分析"]
    return DEMO_SUMMARY, citations, keywords, None


def demo_ppt() -> tuple[str, dict]:
    """Return (pptx_output_path, outline). Renders a real .pptx file."""
    outline = DEMO_PPT_OUTLINE
    output_path = generate_pptx_from_outline(outline, outline["design"])
    return output_path, outline


def demo_analyze(data_file=None, file_context: str = "") -> str:
    """Run a built-in pandas profiling script in the sandbox (no LLM needed).

    If a structured data file is provided, it is analyzed for real and charts
    are produced; otherwise a textual demo summary is returned.
    """
    if data_file is not None:
        code = '''
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = _DATA
print("=== 数据概览 ===")
print(df.shape)
print(df.describe(include="all").to_string())
print("\\n=== 缺失值统计 ===")
print(df.isnull().sum().to_string())

num = df.select_dtypes(include="number")
if len(num.columns) >= 1:
    fig = plt.figure(figsize=(10, 6))
    num.iloc[:, 0].hist(bins=20, color="#1A56E8")
    plt.title(f"Distribution of {num.columns[0]}")
    plt.show()
if len(num.columns) >= 2:
    fig = plt.figure(figsize=(10, 6))
    plt.scatter(num.iloc[:, 0], num.iloc[:, 1], color="#F59E0B", alpha=0.6)
    plt.xlabel(num.columns[0]); plt.ylabel(num.columns[1]); plt.title("Scatter plot")
    plt.show()
    fig = plt.figure(figsize=(10, 6))
    plt.imshow(num.corr(), cmap="coolwarm", aspect="auto"); plt.colorbar(); plt.title("Correlation matrix")
    plt.show()
print("\\n=== Demo 模式说明 ===")
print("以上为内置数据分析脚本输出，无需 API Key 即可运行。")
'''
        result = run_python(code, data_path=data_file.storage_path)
        summary = "## 数据分析结果（Demo 模式）\n\n"
        if result["stdout"]:
            summary += f"**输出：**\n```\n{result['stdout'][:2000]}\n```\n\n"
        if result["error"]:
            summary += f"**错误：** {result['error']}\n\n"
        if result["charts"]:
            summary += f"**生成图表：** {len(result['charts'])} 张\n"
        summary += f"\n**分析代码：**\n```python\n{code[:2000]}\n```"
        return summary

    return (
        "## 数据分析结果（Demo 模式）\n\n"
        "未检测到结构化数据文件（CSV / Excel）。在实际部署中，我会解析你上传的表格、"
        "让 LLM 生成 pandas 分析代码，并在隔离沙箱中执行、捕获图表。\n\n"
        f"已收到的参考内容（前 500 字）：\n```\n{file_context[:500]}\n```"
    )


def demo_codegen(prompt: str, execute: bool = False) -> str:
    code = (
        f"# Demo 模式生成的示例代码（未调用真实 LLM）\n"
        f"# 需求：{prompt}\n\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n\n"
        "def load_and_summarize(path: str) -> pd.DataFrame:\n"
        '    """读取数据并输出基本统计。"""\n'
        "    df = pd.read_csv(path)\n"
        "    print(df.describe(include='all'))\n"
        "    return df\n\n"
        "if __name__ == '__main__':\n"
        '    df = load_and_summarize("data.csv")\n'
        "    df.hist(figsize=(10, 6))\n"
        "    plt.tight_layout()\n"
        "    plt.show()\n"
    )
    result_text = f"```python\n{code}\n```"
    if execute:
        sb = run_python(code)
        result_text += "\n\n### 执行结果\n**输出：**\n```\n" + (sb.get("stdout", "")[:2000] or "(无输出)") + "\n```"
        if sb.get("error"):
            result_text += f"\n**异常：** {sb['error']}"
    return result_text


def demo_translate(text: str, source_lang: str, target_lang: str) -> str:
    return (
        f"[Demo 翻译 · {source_lang} → {target_lang}]\n{text}\n\n"
        "（演示模式：配置 API Key 后，此处将返回真实的模型译文，并保留原排版结构。）"
    )
