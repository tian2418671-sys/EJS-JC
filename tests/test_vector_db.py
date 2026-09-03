"""Unit tests for VectorDB."""
import pytest
from mvu_lint.db.vector_db import VectorDB


def test_init_default_knowledge():
    """Default knowledge initialization should populate knowledge_chunks."""
    db = VectorDB()
    db.init_default_knowledge()
    count = db.conn.execute(
        "SELECT count(*) FROM knowledge_chunks"
    ).fetchone()[0]
    assert count > 0


def test_search_returns_results():
    """Search should return relevant results from the knowledge base."""
    db = VectorDB()
    db.init_default_knowledge()
    results = db.search("EJS 标签", top_k=3)
    assert len(results) > 0
    assert len(results) <= 3
    # Results should have content
    assert all("content" in r for r in results)


def test_error_patterns_inserted():
    """Error patterns should be inserted during initialization."""
    db = VectorDB()
    db.init_default_knowledge()
    count = db.conn.execute(
        "SELECT count(*) FROM error_patterns"
    ).fetchone()[0]
    assert count > 0


def test_init_idempotent():
    """Calling init_default_knowledge twice should not duplicate data."""
    db = VectorDB()
    db.init_default_knowledge()
    count1 = db.conn.execute(
        "SELECT count(*) FROM knowledge_chunks"
    ).fetchone()[0]
    db.init_default_knowledge()
    count2 = db.conn.execute(
        "SELECT count(*) FROM knowledge_chunks"
    ).fetchone()[0]
    assert count1 == count2
