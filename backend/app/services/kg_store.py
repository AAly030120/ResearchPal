"""
GraphRAG store: builds a knowledge graph from extracted entities/triples and
serves graph-aware retrieval for the chat pipeline.

Ported from LitKG's ``kg_store.py`` / ``graphrag.py`` and adapted to
ResearchPal's relational DB + per-user isolation. The NetworkX graph is built
lazily from the DB and cached in-process; it is rebuilt (cheap at demo scale)
whenever new extractions land.
"""
import logging
from typing import Dict, List, Optional, Tuple

import jieba

from app.core.config import settings
from app.models.database import SessionLocal
from app.models.kg import KGEntity, KGTriple, KGCommunity
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# In-process cache: user_id -> (nx.DiGraph, seed_entity_count)
_graph_cache: Dict[str, object] = {}


def _invalidate(user_id: str) -> None:
    _graph_cache.pop(user_id, None)


def _node_key(name: str) -> str:
    return (name or "").strip().lower()


def upsert_extraction(
    user_id: str, file_id: str, entities: List[dict], triples: List[dict]
) -> Tuple[int, int]:
    """Persist extracted entities/triples for a file, replacing any prior graph
    data for that file. Returns (entity_count, triple_count)."""
    db = SessionLocal()
    try:
        db.query(KGTriple).filter(
            KGTriple.user_id == user_id, KGTriple.source_file_id == file_id
        ).delete(synchronize_session=False)
        db.query(KGEntity).filter(
            KGEntity.user_id == user_id, KGEntity.source_file_id == file_id
        ).delete(synchronize_session=False)
        db.commit()

        ent_rows = []
        name_to_row = {}
        for e in entities:
            row = KGEntity(
                user_id=user_id,
                entity_type=e.get("entity_type", "Method"),
                name=e.get("name", "")[:500],
                name_zh=(e.get("name_zh") or "")[:500],
                description=(e.get("description") or "")[:2000],
                properties=e.get("properties") or {},
                source_file_id=file_id,
                source_chunk_ids=e.get("source_chunk_ids") or [],
                community_id=-1,
            )
            db.add(row)
            db.flush()
            name_to_row[_node_key(e.get("name", ""))] = row
            ent_rows.append(row)

        triple_rows = []
        for t in triples:
            skey = _node_key(t.get("source_name", ""))
            tkey = _node_key(t.get("target_name", ""))
            s_row = name_to_row.get(skey)
            t_row = name_to_row.get(tkey)
            triple_rows.append(
                KGTriple(
                    user_id=user_id,
                    relation_type=t.get("relation_type", "USES"),
                    source_name=t.get("source_name", "")[:500],
                    target_name=t.get("target_name", "")[:500],
                    source_entity_id=s_row.id if s_row else None,
                    target_entity_id=t_row.id if t_row else None,
                    description=(t.get("description") or "")[:2000],
                    source_file_id=file_id,
                    confidence=t.get("confidence", 1.0),
                    llm_model=t.get("llm_model", ""),
                )
            )
        db.add_all(triple_rows)
        db.commit()
        _invalidate(user_id)
        return len(ent_rows), len(triple_rows)
    finally:
        db.close()


def _build_graph(user_id: str):
    import networkx as nx

    db = SessionLocal()
    try:
        entities = db.query(KGEntity).filter(KGEntity.user_id == user_id).all()
        triples = db.query(KGTriple).filter(KGTriple.user_id == user_id).all()
    finally:
        db.close()

    g = nx.DiGraph()
    for e in entities:
        g.add_node(
            _node_key(e.name) or f"e:{e.id}",
            name=e.name,
            entity_type=e.entity_type,
            description=e.description or "",
            file_id=e.source_file_id,
        )
    for t in triples:
        s = _node_key(t.source_name)
        tg = _node_key(t.target_name)
        if not s or not tg:
            continue
        if s not in g:
            g.add_node(s, name=t.source_name, entity_type="", description="", file_id=t.source_file_id)
        if tg not in g:
            g.add_node(tg, name=t.target_name, entity_type="", description="", file_id=t.source_file_id)
        g.add_edge(s, tg, relation=t.relation_type, description=t.description or "")
    return g


def get_graph(user_id: str):
    cached = _graph_cache.get(user_id)
    if cached is not None:
        return cached
    g = _build_graph(user_id)
    _graph_cache[user_id] = g
    return g


def stats(user_id: str) -> Dict[str, int]:
    db = SessionLocal()
    try:
        ents = db.query(KGEntity).filter(KGEntity.user_id == user_id).count()
        trips = db.query(KGTriple).filter(KGTriple.user_id == user_id).count()
        comms = db.query(KGCommunity).filter(KGCommunity.user_id == user_id).count()
        return {"entities": ents, "triples": trips, "communities": comms}
    finally:
        db.close()


def _seed_entities(g, query: str, top_k: int = 6) -> List[str]:
    """Pick seed graph nodes by lexical overlap between the query and entity
    names/descriptions (cheap, no extra LLM call)."""
    q_tokens = {
        t for t in jieba.cut(query or "") if t and len(t.strip()) > 1
    }
    if not q_tokens:
        return []
    scored = []
    for n, attrs in g.nodes(data=True):
        text = f"{attrs.get('name', '')} {attrs.get('description', '')}"
        doc_tokens = {t for t in jieba.cut(text) if t and len(t.strip()) > 1}
        overlap = len(q_tokens & doc_tokens)
        if overlap:
            scored.append((overlap, n))
    scored.sort(reverse=True)
    return [n for _, n in scored[:top_k]]


def retrieve_context(
    query: str,
    user_id: str,
    file_ids: Optional[List[str]] = None,
    hops: int = None,
) -> Tuple[str, List[dict]]:
    """Expand the query's seed entities through the graph and return a context
    block plus citation sources. Returns ("", []) when the graph is empty or
    no seed matches."""
    if hops is None:
        hops = settings.KG_RETRIEVAL_HOPS
    g = get_graph(user_id)
    if g.number_of_nodes() == 0:
        return "", []

    seeds = _seed_entities(g, query)
    if not seeds:
        return "", []

    # Expand N-hop subgraph around the seeds.
    sub_nodes = set(seeds)
    frontier = set(seeds)
    for _ in range(max(1, hops)):
        nxt = set()
        for n in frontier:
            nxt.update(g.successors(n))
            nxt.update(g.predecessors(n))
        sub_nodes.update(nxt)
        frontier = nxt

    # Filter by file scope if requested.
    if file_ids:
        fid_set = set(file_ids)
        sub_nodes = {
            n for n in sub_nodes
            if g.nodes[n].get("file_id") in fid_set
            or any(
                g.nodes[m].get("file_id") in fid_set
                for m in list(g.successors(n)) + list(g.predecessors(n))
            )
        }

    lines: List[str] = ["[知识图谱检索结果]"]
    sources: List[dict] = []
    seen: set = set()

    for n in sub_nodes:
        attrs = g.nodes[n]
        if attrs.get("name"):
            lines.append(f"• {attrs.get('entity_type', '实体')}《{attrs['name']}》: {attrs.get('description', '')}")
            if attrs.get("file_id") and attrs["file_id"] not in [s.get("file_id") for s in sources]:
                sources.append({"file_id": attrs["file_id"], "name": attrs.get("name", "")})

    for u, v, edata in g.edges(data=True):
        if u in sub_nodes and v in sub_nodes:
            rel = edata.get("relation", "RELATED")
            desc = edata.get("description", "")
            key = (u, v, rel)
            if key in seen:
                continue
            seen.add(key)
            src = g.nodes[u].get("name", u)
            tgt = g.nodes[v].get("name", v)
            lines.append(f"  - ({rel}) {src} → {tgt}" + (f": {desc}" if desc else ""))

    if len(lines) <= 1:
        return "", []
    return "\n".join(lines), sources


async def detect_communities(user_id: str, model_key: Optional[str] = None) -> int:
    """Run Louvain community detection, persist community ids, and generate a
    short LLM summary per community (GraphRAG global view). Returns #communities."""
    from networkx.algorithms.community import louvain_communities

    g = get_graph(user_id)
    if g.number_of_nodes() == 0:
        return 0
    communities = louvain_communities(g.to_undirected(), seed=42)
    db = SessionLocal()
    try:
        # Reset community ids.
        db.query(KGEntity).filter(KGEntity.user_id == user_id).update(
            {KGEntity.community_id: -1}, synchronize_session=False
        )
        db.query(KGCommunity).filter(KGCommunity.user_id == user_id).delete()
        db.commit()

        model = None
        for cfg in llm_service._model_configs:
            if llm_service._has_key(cfg["key"]):
                model = cfg["key"]
                break

        count = 0
        for cid, members in enumerate(communities):
            names = [g.nodes[m].get("name", m) for m in members if g.nodes[m].get("name")]
            for m in members:
                row = db.query(KGEntity).filter(
                    KGEntity.user_id == user_id,
                    KGEntity.name == g.nodes[m].get("name"),
                ).first()
                if row:
                    row.community_id = cid
            summary = ""
            if model and names:
                try:
                    prompt = (
                        "用 2-3 句中文概括下面这组科研实体共同构成的研究主题或技术方向，"
                        "不要罗列，只讲它们之间的联系：\n" + "、".join(names[:25])
                    )
                    summary = (await _summarize(model, prompt) or "")[:1500]
                except Exception as e:  # pragma: no cover
                    logger.warning("community summary failed: %s", e)
            db.add(KGCommunity(user_id=user_id, community_id=cid,
                               summary=summary, entities=names[:50]))
            count += 1
        db.commit()
        return count
    finally:
        db.close()


async def _summarize(model: str, prompt: str) -> Optional[str]:
    try:
        return await llm_service.chat_complete(
            model, [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=300
        )
    except Exception as e:  # pragma: no cover
        logger.warning("community summary llm failed: %s", e)
        return None
