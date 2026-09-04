"""Unit tests for LLMService (Phase 5 / F7) — all headless, no real model."""
from __future__ import annotations

from pathlib import Path

from mvu_lint.core.llm_service import (
    LLMService,
    default_models_dir,
    find_default_model,
)


def test_default_models_dir_is_path():
    assert isinstance(default_models_dir(), Path)


def test_find_default_model_empty_dir(tmp_path):
    assert find_default_model(tmp_path) is None


def test_find_default_model_prefers_qwen(tmp_path):
    (tmp_path / "b.gguf").write_bytes(b"")
    (tmp_path / "qwen2.5-1.5b-instruct-q4_k_m.gguf").write_bytes(b"")
    found = find_default_model(tmp_path)
    assert found is not None
    assert "qwen" in found.name.lower()


def test_service_idle_by_default():
    service = LLMService()
    assert not service.available
    assert service.status == "idle"


def test_load_missing_model_fails():
    service = LLMService(model_path=str(Path("nonexistent.gguf")))
    assert service.load() is False
    assert not service.available
    assert service.load_error
    assert service.status == "error"


def test_load_no_model_dir_fails():
    service = LLMService()  # no explicit path → search default dir
    # find_default_model returns None in CI (no models dir populated)
    assert service.load() is False
    assert "模型" in service.load_error


def test_generate_without_model_returns_none():
    service = LLMService()
    assert service.generate("hello") is None


def test_unload_resets_state():
    service = LLMService()
    service.unload()
    assert not service.available
    assert service.load_error == ""
    assert service.status == "idle"
