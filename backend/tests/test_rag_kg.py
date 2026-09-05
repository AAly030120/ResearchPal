"""
Logic tests for the RAG Top-3 enhancements and the GraphRAG (LitKG) fusion.

These exercise the *pure logic* and *orchestration* of:
  * parent-child chunking (page-level slicing + grounded parent context)
  * the cross-encoder reranker's graceful fallback when fastembed is absent
  * GraphRAG N-hop retrieval expansion over an in-memory knowledge graph
  * the deep-research agent pipeline (plan -> retrieve -> synthesize -> refs)

External services (real LLM, embedding model, Chroma) are mocked so the suite
runs anywhere without API keys or GPU.
"""
import asyncio
import os
import sys

# Ensure the backend package is importable.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_rag_kg.db")
os.environ.setdefault("CORS_ORIGINS", "*")

import networkx as nx
import pytest

from app.services.rag_service import chunk_parent_child
from app.services.reranker import reranker
from app.services import kg_store
from app.services.research_service import research_stream


# --------------------------------------------------------------------------- #
# 1. Parent-child chunking
# --------------------------------------------------------------------------- #
def test_chunk_parent_child_basic():
    text = "第一段内容较长需要被切分的内容用于验证子块生成逻辑是否正常工作。\n\n第二段是另一个独立的段落用于测试边界情况。"
    items = chunk_parent_child(text, child_size=20, parent_size=200, overlap=4)
    assert len(items) >= 2
    for it in items:
        assert "child" in it and "parent" in it and "page" in it
        assert it["child"].strip() and it["parent"].strip()
        # parent never exceeds the configured parent window
        assert len(it["parent"]) <= 200 + 1
        # child (with its overlap tail) stays within child_size + overlap
        assert len(it["child"]) <= 20 + 4 + 5
        assert it["page"] == 0  # no pages supplied


def test_chunk_parent_child_pages():
    pages = ["第一页第一段。第一页第二段。", "第二页只有一段较长的文本内容用于验证页码是否正确映射到对应的子块上。"]
    items = chunk_parent_child("\n\n".join(pages), child_size=15, parent_size=100, overlap=2, pages=pages)
    assert items
    # Every item must carry a valid page number (1-based)
    assert all(it["page"] in (1, 2) for it in items)
    # At least one chunk must be attributed to page 2
    assert any(it["page"] == 2 for it in items)


def test_chunk_parent_child_empty():
    assert chunk_parent_child("") == []
    assert chunk_parent_child("   \n  ") == []


# --------------------------------------------------------------------------- #
# 2. Cross-encoder reranker fallback
# --------------------------------------------------------------------------- #
def test_reranker_falls_back_without_fastembed():
    """Without fastembed installed, rerank() must return None (heuristic path)."""
    # In this test environment fastembed is intentionally not installed.
    assert reranker.available is False
    scores = reranker.rerank("测试查询", ["文档一内容", "文档二内容"])
    assert scores is None


# --------------------------------------------------------------------------- #
# 3. GraphRAG N-hop retrieval expansion
# --------------------------------------------------------------------------- #
def _build_sample_graph():
    g = nx.DiGraph()
    g.add_node("深度学习", name="深度学习", entity_type="Method",
               description="深度学习 是 神经网络 训练 方法", file_id="f1")
    g.add_node("神经网络", name="神经网络", entity_type="Concept",
               description="神经网络 由 神经元 组成", file_id="f1")
    g.add_node("卷积网络", name="卷积网络", entity_type="Method",
               description="卷积网络 用于 图像", file_id="f1")
    g.add_edge("深度学习", "神经网络", relation="USES", description="深度学习使用神经网络")
    g.add_edge("深度学习", "卷积网络", relation="INCLUDES", description="卷积网络是深度学习的一种")
    return g


def test_kg_retrieve_expands_neighbors():
    user_id = "kg-test-user-1"
    kg_store._graph_cache[user_id] = _build_sample_graph()
    try:
        ctx, sources = kg_store.retrieve_context("深度学习 的应用", user_id, file_ids=["f1"])
        assert ctx, "expected non-empty graph context"
        assert "深度学习" in ctx
        # 1-hop expansion must surface the neighbor 神经网络
        assert "神经网络" in ctx
        assert any(s.get("file_id") == "f1" for s in sources)
    finally:
        kg_store._graph_cache.pop(user_id, None)


def test_kg_retrieve_no_seed_returns_empty():
    user_id = "kg-test-user-2"
    kg_store._graph_cache[user_id] = _build_sample_graph()
    try:
        # Query with no lexical overlap -> no seeds -> empty result
        ctx, sources = kg_store.retrieve_context("量子计算 与 区块链 无关主题", user_id)
        assert ctx == "" and sources == []
    finally:
        kg_store._graph_cache.pop(user_id, None)


# --------------------------------------------------------------------------- #
# 4. Deep-research agent pipeline (LLM + retrieval mocked)
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_research_deps(monkeypatch):
    import app.services.research_service as rs

    # RAG retrieval (mocked)
    monkeypatch.setattr(rs.rag_service, "has_documents", lambda uid: True)
    monkeypatch.setattr(
        rs.rag_service, "retrieve",
        lambda uid, q, file_ids=None: [{"document": "片段文本", "metadata": {"file_id": "f1"}}],
    )
    monkeypatch.setattr(
        rs.rag_service, "format_context",
        lambda hits: ("[资料] 片段文本", [{"file": "doc.pdf", "chunk": 1, "page": 2, "text": "片段文本"}]),
    )
    # KG graph (empty -> KG branch skipped, RAG branch still works)
    monkeypatch.setattr(rs, "get_graph", lambda uid: nx.DiGraph())
    monkeypatch.setattr(rs, "kg_retrieve", lambda q, uid, file_ids=None: ("", []))

    # LLM mocks
    monkeypatch.setattr(
        rs.llm_service, "chat_complete",
        lambda model, messages, temperature=0.3, max_tokens=400: "1. 子方向A\n2. 子方向B\n3. 子方向C",
    )

    async def fake_stream(model, messages, temperature=0.3, max_tokens=1200):
        for w in ["段落一内容", "段落一继续"]:
            yield w

    monkeypatch.setattr(rs.llm_service, "chat_stream", fake_stream)
    return rs


def test_research_pipeline_runs(mock_research_deps):
    events = []
    async def collect():
        async for ev in research_stream("研究主题X", "u1", "gpt-4o-mini", file_ids=["f1"]):
            events.append(ev)

    asyncio.run(collect())

    stages = [e for e in events if e.get("stage")]
    chunks = [e for e in events if e.get("chunk")]
    dones = [e for e in events if e.get("done")]

    assert any(s["stage"] == "plan" for s in stages), "expected a plan stage"
    assert any(s["stage"] == "refs" for s in stages), "expected a references stage"
    assert len(chunks) > 0, "expected streamed chunks"
    assert len(dones) == 1, "expected exactly one done event"
    done = dones[0]
    assert done["content"]
    assert "研究大纲" in done["content"]
    assert done["retrieved_count"] >= 1
    assert done["sources"], "expected reference sources to be attached"
