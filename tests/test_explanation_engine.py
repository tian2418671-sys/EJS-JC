"""Unit tests for ExplanationEngine (Phase 5 / F7)."""
from __future__ import annotations

from mvu_lint.core.explanation_engine import ExplanationEngine, ExplanationResult
from mvu_lint.db.vector_db import VectorDB


class _FakeLLM:
    """Minimal LLMService stand-in that always succeeds."""

    available = True
    model_path = "/models/qwen.gguf"

    def generate(self, prompt, max_tokens=512, temperature=0.3, timeout=None):
        return "根因分析：标签未闭合。修复步骤：补上 %>。"


class _FakeRAG:
    def __init__(self):
        self.vdb = VectorDB()
        self.vdb.init_default_knowledge()

    def search(self, query, top_k=3):
        return self.vdb.search(query, top_k=top_k)


_SAMPLE_ERROR = {
    "error_id": "EJS-0001",
    "level": "Lv.1",
    "category": "EJS",
    "file_path": "世界书/index.yaml",
    "line_number": 12,
    "path": "主角.好感度",
    "message": "EJS 标签未闭合",
    "suggestion": "补上 %> 闭合标签",
}


def test_template_explain_without_llm():
    engine = ExplanationEngine(llm=None, rag=None)
    # llm=None → default LLMService (not loaded) → template path
    result = engine.explain(_SAMPLE_ERROR, use_llm=False)
    assert isinstance(result, ExplanationResult)
    assert result.source == "template"
    assert "根因分析" in result.explanation
    assert result.explanation


def test_template_explain_forced_even_with_llm():
    engine = ExplanationEngine(llm=_FakeLLM(), rag=None)
    result = engine.explain(_SAMPLE_ERROR, use_llm=False)
    assert result.source == "template"
    assert "修复建议" in result.explanation


def test_llm_explain_when_available():
    engine = ExplanationEngine(llm=_FakeLLM(), rag=None)
    result = engine.explain(_SAMPLE_ERROR, use_llm=True)
    assert result.source == "llm"
    assert "根因分析" in result.explanation
    assert result.model


def test_fallback_to_template_when_llm_unavailable():
    engine = ExplanationEngine(llm=LLMServiceUnavailable(), rag=None)
    result = engine.explain(_SAMPLE_ERROR, use_llm=True)
    assert result.source == "template"


def test_rag_retrieval_populates_chunks():
    engine = ExplanationEngine(llm=_FakeLLM(), rag=_FakeRAG())
    result = engine.explain(_SAMPLE_ERROR, use_llm=True)
    assert result.source == "llm"
    assert len(result.chunks) > 0


def test_to_dict_shape():
    engine = ExplanationEngine(llm=_FakeLLM(), rag=None)
    data = engine.explain(_SAMPLE_ERROR, use_llm=True).to_dict()
    assert data["error_id"] == "EJS-0001"
    assert "explanation" in data
    assert "source" in data
    assert "chunks" in data


class LLMServiceUnavailable:
    """LLM stand-in whose model never loads."""

    available = False
    model_path = None

    def generate(self, prompt, **kwargs):
        return None
