"""
Knowledge-graph extraction (GraphRAG), ported & adapted from the LitKG project.

Given document text, an LLM extracts typed entities (10 types) and relations
(10 standardized relation types) as a structured JSON object. Each entity/relation
carries a human-readable ``description`` so the resulting graph is queryable and
answers stay grounded.

The heavy lifting reuses ResearchPal's ``llm_service`` (OpenAI-compatible, all
providers) instead of LitKG's standalone OpenAI client.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


# ── Relation normalization (ported verbatim from LitKG models.py) ──────────
_RELATION_NORMALIZE_MAP = {
    "PROPOSES_METHOD": "PROPOSES", "PROPOSES_MODEL": "PROPOSES",
    "PROPOSES_APPROACH": "PROPOSES", "PROPOSES_FRAMEWORK": "PROPOSES",
    "USES_DATASET": "USES", "USES_METHOD": "USES", "USES_MODEL": "USES",
    "EVALUATED_ON_DATASET": "EVALUATED_ON", "EVALUATED_ON_BENCHMARK": "EVALUATED_ON",
    "OUTPERFORMS_MODEL": "OUTPERFORMS", "OUTPERFORMS_METHOD": "OUTPERFORMS",
    "OUTPERFORMS_BASELINE": "OUTPERFORMS",
    "ACHIEVES_RESULT": "ACHIEVES", "ACHIEVES_PERFORMANCE": "ACHIEVES",
    "BELONGS_TO_INSTITUTION": "BELONGS_TO", "BELONGS_TO_DOMAIN": "BELONGS_TO",
    "EXTENDS_METHOD": "EXTENDS", "EXTENDS_MODEL": "EXTENDS",
    "COMPARED_WITH_METHOD": "COMPARED_WITH", "COMPARED_WITH_MODEL": "COMPARED_WITH",
    "EVALUATED_BY_METRIC": "EVALUATED_BY", "AUTHORED_BY_AUTHOR": "AUTHORED_BY",
}
_VALID_RELATIONS = {
    "PROPOSES", "USES", "EVALUATED_ON", "OUTPERFORMS", "ACHIEVES",
    "BELONGS_TO", "EXTENDS", "COMPARED_WITH", "EVALUATED_BY", "AUTHORED_BY",
}


def normalize_relation_type(raw: str) -> str:
    if not raw:
        return ""
    upper = raw.strip().upper()
    if upper in _RELATION_NORMALIZE_MAP:
        return _RELATION_NORMALIZE_MAP[upper]
    if upper in _VALID_RELATIONS:
        return upper
    base = upper.split("_")[0] if "_" in upper else upper
    if base in _VALID_RELATIONS:
        return base
    for key in sorted(_VALID_RELATIONS, key=len, reverse=True):
        if key in upper:
            return key
    return upper


SYSTEM_PROMPT = (
    "You are an expert NLP/ML research literature analyst. "
    "Your task is to extract structured entities and relations from the provided "
    "document text. Always output valid JSON only."
)

EXTRACTION_TEMPLATE = """You are an expert NLP/ML research literature analyst. Extract structured entities and relations from the provided document text.

## Entity Types (extract ALL applicable types):
- **Paper/Document**: The work itself. Attributes: title, year, venue, abstract.
- **Author**: Authors. Attributes: name, affiliation if mentioned.
- **Institution**: Research institutions or companies.
- **Method**: Any technical method, approach, algorithm, or technique.
- **Task**: The task addressed (e.g. "Question Answering", "Link Prediction").
- **Dataset**: Datasets used for experiments or evaluation.
- **Model**: Specific model architecture or pre-trained model (e.g. "BERT-base").
- **Metric**: Evaluation metrics (e.g. "F1 Score", "Accuracy", "Hits@10").
- **Result**: Key experimental results with values.
- **Domain**: Research domain or subfield (e.g. "Knowledge Graph", "NLP").

## CRITICAL — Entity Description (most important field):
- Provide a "description" (one concise English sentence) for EVERY entity, of EVERY type.
- The description must state what the entity IS and why it matters in context.
- Do NOT leave description empty except for trivial entities.

## Language rule (ENFORCE STRICTLY):
- ALL entity "name" fields MUST be in English (standardized international names).
- If the document is Chinese, put the original Chinese name in "name_zh".
- RELATIONS: "source" and "target" MUST reference English names exactly.

## Relation Types (STANDARDIZED uppercase ONLY):
- Paper/Document -[AUTHORED_BY]-> Author
- Author -[BELONGS_TO]-> Institution
- Paper/Method/Model -[PROPOSES]-> Method/Model
- Method/Model -[USES]-> Dataset/Method/Model
- Method/Model -[EVALUATED_ON]-> Dataset
- Method/Model -[OUTPERFORMS]-> Method/Model
- Method/Model -[ACHIEVES]-> Result
- Method/Model -[BELONGS_TO]-> Domain
- Method/Model -[EXTENDS]-> Method/Model
- Method/Model -[COMPARED_WITH]-> Method/Model
- Method/Model -[EVALUATED_BY]-> Metric

## Output Format:
Return ONLY a valid JSON object. No markdown, no code fences.

{
  "document": {"title": "...", "year": 2024, "venue": "...", "abstract": "...", "description": "..."},
  "authors": [{"name": "...", "name_zh": "", "affiliation": "...", "description": "..."}],
  "methods": [{"name": "...", "name_zh": "", "description": "..."}],
  "models": [{"name": "...", "name_zh": "", "param_count": "", "description": "..."}],
  "datasets": [{"name": "...", "name_zh": "", "size": "", "domain": "", "description": "..."}],
  "tasks": [{"name": "...", "name_zh": "", "description": "..."}],
  "metrics": [{"name": "...", "name_zh": "", "description": "..."}],
  "results": [{"method": "...", "dataset": "...", "metric": "...", "value": "", "description": "..."}],
  "relations": [
    {"type": "PROPOSES", "source": "...", "target": "...", "description": "..."},
    {"type": "USES", "source": "...", "target": "...", "description": "..."}
  ]
}

## Rules:
1. ALL "name" values in English; use "name_zh" for Chinese names.
2. "source"/"target" must reference English entity names exactly.
3. Extract methods the document PROPOSES as its own contribution; exclude related work.
4. Only include results with explicit numeric values.
5. If a type has no data, return an empty array.

## Document Content:
{content}
"""


def _pick_model(requested: Optional[str]) -> Optional[str]:
    """Return a model key that has a usable API key, preferring ``requested``."""
    if requested and llm_service._has_key(requested):
        return requested
    if settings.KG_EXTRACTION_MODEL and llm_service._has_key(settings.KG_EXTRACTION_MODEL):
        return settings.KG_EXTRACTION_MODEL
    for cfg in llm_service._model_configs:
        if llm_service._has_key(cfg["key"]):
            return cfg["key"]
    return None


def _clean_json(raw: str) -> str:
    """Strip markdown fences / leading prose from an LLM JSON response."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    # Take the first {...} block if extra text slipped in.
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    return s


async def extract_kg(text: str, model_key: Optional[str] = None) -> Dict[str, Any]:
    """Extract entities + triples from ``text``. Returns {"entities":[], "triples":[]}."""
    model = _pick_model(model_key)
    empty = {"entities": [], "triples": []}
    if not model:
        logger.info("KG extraction skipped: no API key configured")
        return empty
    prompt = EXTRACTION_TEMPLATE.format(content=text[:12000])
    try:
        raw = await llm_service.chat_complete(
            model,
            [{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=4096,
        )
    except Exception as e:
        logger.warning("KG extraction LLM call failed: %s", e)
        return empty

    try:
        data = json.loads(_clean_json(raw))
    except Exception as e:
        logger.warning("KG extraction JSON parse failed: %s", e)
        return empty

    entities: List[Dict[str, Any]] = []
    triples: List[Dict[str, Any]] = []

    def _name(d: Dict[str, Any], fallback: str) -> str:
        return (d.get("name") or "").strip() or fallback

    doc = data.get("document") or {}
    if doc.get("title"):
        entities.append({
            "entity_type": "Paper", "name": doc["title"],
            "name_zh": doc.get("title_zh", ""),
            "description": doc.get("description") or doc.get("abstract") or "",
        })
    for auth in data.get("authors", []):
        entities.append({"entity_type": "Author", "name": _name(auth, "Author"),
                         "name_zh": auth.get("name_zh", ""),
                         "description": auth.get("description", "")})
    for bucket in ("methods", "models", "datasets", "tasks", "metrics"):
        for e in data.get(bucket, []):
            etype = {"methods": "Method", "models": "Model", "datasets": "Dataset",
                     "tasks": "Task", "metrics": "Metric"}[bucket]
            entities.append({"entity_type": etype, "name": _name(e, etype),
                             "name_zh": e.get("name_zh", ""),
                             "description": e.get("description", "")})
    for r in data.get("results", []):
        entities.append({"entity_type": "Result",
                         "name": f"{r.get('method','')}→{r.get('metric','')}={r.get('value','')}".strip("→="),
                         "description": r.get("description", "")})

    name_index: Dict[str, str] = {e["name"].lower(): e["name"] for e in entities}
    for rel in data.get("relations", []):
        rtype = normalize_relation_type(rel.get("type", ""))
        if rtype not in _VALID_RELATIONS:
            continue
        sname = rel.get("source", "").strip()
        tname = rel.get("target", "").strip()
        if not sname or not tname:
            continue
        triples.append({
            "relation_type": rtype, "source_name": sname, "target_name": tname,
            "description": rel.get("description", ""), "llm_model": model,
        })

    # Cap entities to keep storage/search bounded per document.
    entities = entities[: settings.KG_MAX_ENTITIES_PER_FILE]
    return {"entities": entities, "triples": triples}
