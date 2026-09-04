"""Tests for the Phase 3 rule-driven simulation engine."""
from __future__ import annotations

import pytest

from mvu_lint.core.simulation_engine import SimulationEngine


@pytest.fixture
def minimal_entries():
    return [
        {
            "file_path": "世界书/开场",
            "content": "世界初始化为夜晚。<!-- mvu: 世界.时辰 = 夜晚 -->",
        },
        {
            "file_path": "世界书/幕间",
            "content": "@@if getvar('stat_data.世界.当前幕').includes('第二幕')\n"
                       "<!-- mvu: 世界.当前幕 = 第二幕·觉醒 -->",
        },
    ]


def test_initial_state_from_initvar():
    engine = SimulationEngine([], {"世界": {"当前幕": "第一幕"}, "主角": {"hp": 10}})
    assert engine.state.get("世界.当前幕") == "第一幕"
    assert engine.state.get("主角.hp") == 10


def test_mvu_comment_assignment():
    engine = SimulationEngine([{
        "file_path": "世界书/a",
        "content": "<!-- mvu: 主角.hp = 20 -->",
    }], {"主角": {"hp": 10}})
    result = engine.step("")
    assert len(result.commands) == 1
    assert result.commands[0].status == "applied"
    assert result.commands[0].after == 20
    assert "主角.hp" in result.changed_paths


def test_condition_activation_with_getvar():
    engine = SimulationEngine([{
        "file_path": "世界书/幕间",
        "content": "@@if getvar('stat_data.世界.当前幕').includes('第一幕')\n"
                   "<!-- mvu: 主角.hp += 5 -->",
    }], {"世界": {"当前幕": "第一幕"}, "主角": {"hp": 10}})
    result = engine.step("")
    assert "世界书/幕间" in result.activated_entries
    assert result.commands[0].after == 15


def test_condition_not_met_does_not_activate():
    engine = SimulationEngine([{
        "file_path": "世界书/幕间",
        "content": "@@if getvar('stat_data.世界.当前幕').includes('第二幕')\n"
                   "<!-- mvu: 主角.hp += 5 -->",
    }], {"世界": {"当前幕": "第一幕"}, "主角": {"hp": 10}})
    result = engine.step("")
    assert "世界书/幕间" not in result.activated_entries
    assert not result.commands


def test_json_patch_add_and_replace():
    engine = SimulationEngine([{
        "file_path": "世界书/a",
        "content": "<UpdateVariable>\n"
                   "<JSONPatch>\n"
                   '[{"op":"add","path":"/主角/道具","value":"剑"},'
                   ' {"op":"replace","path":"/主角/hp","value":30}]\n'
                   "</JSONPatch>\n"
                   "</UpdateVariable>",
    }], {"主角": {"hp": 10}})
    result = engine.step("")
    assert len(result.commands) == 2
    assert all(c.status == "applied" for c in result.commands)
    assert engine.state.get("主角.道具") == "剑"
    assert engine.state.get("主角.hp") == 30


def test_run_stops_when_stable():
    engine = SimulationEngine([{
        "file_path": "世界书/a",
        "content": "<!-- mvu: 主角.hp = 5 -->",
    }], {"主角": {"hp": 10}})
    results = engine.run(max_steps=10)
    # Engine appends the stable step before stopping so the caller can see the
    # final state; therefore a single changing step produces two results.
    assert len(results) == 2
    assert "主角.hp" in results[0].changed_paths
    assert not results[1].changed_paths  # final state is stable


def test_run_with_user_inputs():
    engine = SimulationEngine([{
        "file_path": "世界书/输入触发",
        "content": "<!-- mvu: 主角.输入 = {{user_input}} -->",
    }], {"主角": {"输入": ""}})
    # Since the template is not interpolated, no commands fire; 
    # but the inputs are consumed one per step.
    results = engine.run(max_steps=10, user_inputs=["hello", "world"])
    assert [r.user_input for r in results[:2]] == ["hello", "world"]


def test_snapshot_deep_copy_isolation():
    engine = SimulationEngine([], {"主角": {"hp": 10}})
    snap1 = engine.state.snapshot()
    engine.state.apply_mvu_comment("主角.hp", "=", 99)
    snap2 = engine.state.snapshot()
    assert snap1["主角"]["hp"] == 10
    assert snap2["主角"]["hp"] == 99


def test_error_on_invalid_json_pointer():
    engine = SimulationEngine([{
        "file_path": "世界书/a",
        "content": '<UpdateVariable>\n<JSONPatch>[{"op":"replace","path":"bad","value":1}]</JSONPatch>\n</UpdateVariable>',
    }], {"a": 1})
    result = engine.step("")
    assert len(result.commands) == 1
    assert result.commands[0].status == "error"
    assert result.errors
