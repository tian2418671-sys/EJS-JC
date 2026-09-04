"""Tests for AppController simulation integration (Phase 3 / F4-F5)."""
from __future__ import annotations

import json

import pytest

from mvu_lint.controllers.app_controller import AppController


@pytest.fixture
def card_json(tmp_path):
    """Build a minimal role-card JSON (chara_card_v2)."""
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "测试角色卡",
            "description": "# 变量初始值（由 mvu 在开始时读取）\n主角:\n  hp: 10\n",
            "first_mes": "你好",
            "extensions": {},
            "character_book": {
                "name": "世界书",
                "entries": [
                    {
                        "id": "e1",
                        "keys": ["测试"],
                        "comment": "测试条目",
                        "content": "<!-- mvu: 主角.hp = 20 -->",
                    },
                ],
            },
        },
    }
    path = tmp_path / "test_card.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_run_simulation_without_card_raises():
    controller = AppController()
    with pytest.raises(RuntimeError):
        controller.run_simulation()
    controller.close()


def test_simulation_persists_rounds_and_snapshots(card_json):
    controller = AppController()
    controller.import_card(card_json)

    results = controller.run_simulation(max_steps=3)
    # run stops as soon as the state stabilizes; a single changed path yields
    # the change step + one stable step.
    assert len(results) == 2

    rounds = controller.get_simulation_rounds()
    assert len(rounds) == 2
    assert {r["round_number"] for r in rounds} == {1, 2}

    snapshots = controller.get_state_snapshots()
    assert len(snapshots) == 2
    assert all("stat_data" in s for s in snapshots)

    logs = controller.get_simulation_logs()
    # Logs depend on card content; just verify the table is queried.
    assert isinstance(logs, list)

    controller.close()


def test_clear_simulation_removes_data(card_json):
    controller = AppController()
    controller.import_card(card_json)

    controller.run_simulation(max_steps=2)
    controller.clear_simulation()

    assert controller.get_simulation_rounds() == []
    assert controller.get_state_snapshots() == []
    assert controller.get_simulation_logs() == []

    controller.close()
