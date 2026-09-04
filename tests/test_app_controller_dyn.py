"""Tests for AppController dynamic analysis (Phase 4 / F6)."""
from __future__ import annotations

import json

import pytest

from mvu_lint.controllers.app_controller import AppController


@pytest.fixture
def card_json(tmp_path):
    """Card whose first round contains a command failure + type drift.

    initvar: 主角.hp = 10 (int).  Round 1 replaces it with a string via a
    += on a non-numeric path to force an error, and sets hp to "满血" to
    trigger type drift.
    """
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "测试角色卡",
            "description": (
                "# 变量初始值（由 mvu 在开始时读取）\n"
                "主角:\n"
                "  hp: 10\n"
            ),
            "first_mes": "你好",
            "extensions": {},
            "character_book": {
                "name": "世界书",
                "entries": [
                    {
                        "id": "e1",
                        "keys": [],
                        "comment": "类型漂移",
                        "content": "<!-- mvu: 主角.hp = 满血 -->",
                    },
                    {
                        "id": "e2",
                        "keys": [],
                        "comment": "命令失败",
                        "content": "<!-- mvu: 主角.不存在的字段 += 5 -->",
                    },
                ],
            },
        },
    }
    path = tmp_path / "dyn_card.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_run_dynamic_analysis_without_simulation_returns_empty(card_json):
    controller = AppController()
    controller.import_card(card_json)
    assert controller.run_dynamic_analysis() == []
    controller.close()


def test_run_dynamic_analysis_finds_failures_and_drift(card_json):
    controller = AppController()
    controller.import_card(card_json)
    controller.run_simulation(max_steps=2)

    findings = controller.run_dynamic_analysis()
    messages = " ".join(f["message"] for f in findings)
    levels = {f["level"] for f in findings}

    # R1: the += on a missing path must surface as a Lv.2 command failure.
    assert any("命令执行失败" in f["message"] for f in findings)
    assert "Lv.2" in levels
    # R3: hp changed from int to str.
    assert any("类型漂移" in f["message"] for f in findings)

    # Findings are persisted and queryable.
    stored = controller.get_dynamic_findings()
    assert len(stored) == len(findings)
    assert all(f["category"] == "动态" for f in stored)

    controller.close()


def test_clear_dynamic_findings(card_json):
    controller = AppController()
    controller.import_card(card_json)
    controller.run_simulation(max_steps=2)
    controller.run_dynamic_analysis()
    assert len(controller.get_dynamic_findings()) > 0

    controller.clear_dynamic_findings()
    assert controller.get_dynamic_findings() == []
    controller.close()


def test_dynamic_status_roundtrip(card_json):
    controller = AppController()
    controller.import_card(card_json)
    controller.run_simulation(max_steps=2)
    controller.run_dynamic_analysis()

    first = controller.get_dynamic_findings()[0]
    fid = first["error_id"]
    assert controller.set_dynamic_status(fid, "fixed") is True
    stored = {f["error_id"]: f for f in controller.get_dynamic_findings()}
    assert stored[fid]["status"] == "fixed"

    assert controller.set_dynamic_status("DYN-NOPE", "fixed") is False
    controller.close()


def test_run_dynamic_analysis_idempotent(card_json):
    """Re-running analysis clears old findings first (no duplicates)."""
    controller = AppController()
    controller.import_card(card_json)
    controller.run_simulation(max_steps=2)

    controller.run_dynamic_analysis()
    n1 = len(controller.get_dynamic_findings())
    controller.run_dynamic_analysis()
    n2 = len(controller.get_dynamic_findings())
    assert n1 == n2
    controller.close()
