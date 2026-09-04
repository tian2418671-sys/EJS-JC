"""Unit tests for RAGService (Phase 5 / F7)."""
from __future__ import annotations

from mvu_lint.core.rag_service import RAGService, default_knowledge_db_path


def test_default_db_path_is_under_appdata_dir():
    path = default_knowledge_db_path()
    assert path.name == "knowledge.db"
    assert "MvuEjsLinter" in str(path)


def test_seeds_default_knowledge(tmp_path):
    rag = RAGService(db_path=str(tmp_path / "knowledge.db"))
    try:
        assert rag.chunk_count() > 0
    finally:
        rag.close()


def test_search_returns_results(tmp_path):
    rag = RAGService(db_path=str(tmp_path / "knowledge.db"))
    try:
        results = rag.search("EJS 标签", top_k=3)
        assert len(results) > 0
        assert all("content" in r for r in results)
    finally:
        rag.close()


def test_add_chunk_increases_count(tmp_path):
    rag = RAGService(db_path=str(tmp_path / "knowledge.db"))
    try:
        before = rag.chunk_count()
        rag.add_chunk("自定义知识：<UpdateVariable> 用于 JSON Patch 更新。",
                      title="自定义条目")
        assert rag.chunk_count() == before + 1
    finally:
        rag.close()
