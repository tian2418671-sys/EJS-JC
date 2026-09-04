"""AppController explain_error tests (Phase 5 / F7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvu_lint.controllers.app_controller import AppController
from mvu_lint.core.rag_service import RAGService


@pytest.fixture
def card_json(tmp_path: Path) -> str:
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试角色卡",
        "data": {
            "name": "测试角色卡",
            "extensions": {},
            "character_book": {
                "name": "世界书",
                "entries": [
                    {"id": "e1", "keys": ["坏"], "comment": "未闭合标签",
                     "content": "<p>未闭合：<%= stat_data.主角.好感度", "enabled": True},
                    {"id": "e2", "keys": ["初始值"], "comment": "变量初始值",
                     "content": "# 变量初始值\n主角:\n  好感度: 0\n", "enabled": True},
                ],
            },
        },
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def controller_with_errors(card_json, tmp_path):
    controller = AppController()
    rag = RAGService(db_path=str(tmp_path / "kb.db"))
    controller.import_card(card_json)
    controller.run_static_check()
    # Isolate the RAG knowledge base to a temp path (avoid touching APPDATA).
    controller._rag_service = rag
    yield controller
    controller.close()
    rag.close()


def test_explain_error_returns_dict(controller_with_errors):
    errors = controller_with_errors.get_errors()
    assert errors
    eid = errors[0]["error_id"]
    result = controller_with_errors.explain_error(eid)
    assert result is not None
    assert result["error_id"] == eid
    assert result["explanation"]
    assert result["source"] == "template"  # no LLM model in tests


def test_explain_error_persists_explanation(controller_with_errors):
    eid = controller_with_errors.get_errors()[0]["error_id"]
    controller_with_errors.explain_error(eid)
    stored = controller_with_errors.get_explanation(eid)
    assert stored
    assert "根因分析" in stored


def test_explain_unknown_id_returns_none(controller_with_errors):
    assert controller_with_errors.explain_error("NOPE-9999") is None
    assert controller_with_errors.get_explanation("NOPE-9999") is None


def test_explain_all_errors(controller_with_errors):
    for e in controller_with_errors.get_errors():
        result = controller_with_errors.explain_error(e["error_id"])
        assert result is not None
        assert result["explanation"]
