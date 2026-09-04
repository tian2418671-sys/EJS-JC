"""Tests for the dynamic locator (Phase 4 / F6)."""
from __future__ import annotations

import json

import pytest

from mvu_lint.core.debugger import DynamicLocator, norm_path
from mvu_lint.models.check_result import ErrorLevel


def _round(rid: int, round_no: int) -> dict:
    return {"id": rid, "round_number": round_no}


def _snap(rid: int, data: dict, changed: list) -> dict:
    return {
        "round_id": rid,
        "stat_data": json.dumps(data, ensure_ascii=False),
        "changed_paths": json.dumps(changed, ensure_ascii=False),
    }


def _log(rid: int, path: str, op: str = "=", status: str = "applied",
         file_path: str = "世界书/e1", error: str = "",
         before=None, after=None) -> dict:
    return {
        "round_id": rid,
        "file_path": file_path,
        "command_type": "mvu",
        "path": path,
        "op": op,
        "value": json.dumps(after),
        "before_value": json.dumps(before),
        "after_value": json.dumps(after),
        "status": status,
        "error": error,
    }


# ── norm_path ──────────────────────────────────────────────────────────

def test_norm_path_strips_stat_data_prefix():
    assert norm_path("stat_data.主角.好感度") == "主角.好感度"
    assert norm_path("data.主角.好感度") == "主角.好感度"
    assert norm_path("locals.主角.好感度") == "主角.好感度"


def test_norm_path_json_pointer():
    # "/data/…" resolves to the same variable root as "stat_data." → stripped.
    assert norm_path("/data/主角/好感度") == "主角.好感度"
    assert norm_path("/主角/好感度") == "主角.好感度"


def test_norm_path_array_accessor():
    assert norm_path("stat_data.物品[0]") == "物品.0"


# ── R1: command failures ───────────────────────────────────────────────

def test_r1_command_failure_is_lv2():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"主角": {"hp": 10}}, [])]
    logs = [_log(1, "主角.hp", op="+=", status="error", error="类型不匹配")]
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    assert len(findings) == 1
    f = findings[0]
    assert f.level == ErrorLevel.LV2
    assert f.round_number == 1
    assert f.path == "主角.hp"
    assert "类型不匹配" in f.message


def test_r1_successful_commands_produce_no_finding():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"主角": {"hp": 20}}, ["主角.hp"])]
    logs = [_log(1, "主角.hp", op="=", status="applied", before=10, after=20)]
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    assert findings == []


# ── R2: variable disappearance ─────────────────────────────────────────

def test_r2_variable_disappears():
    rounds = [_round(1, 1), _round(2, 2)]
    snaps = [
        _snap(1, {"主角": {"hp": 10, "name": "阿明"}}, ["主角.hp"]),
        _snap(2, {"主角": {"hp": 10}}, ["主角.name"]),
    ]
    logs = [
        _log(1, "主角.hp", op="=", status="applied", before=0, after=10),
        _log(2, "主角.name", op="remove", status="applied"),
    ]
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    disappearance = [f for f in findings if "丢失" in f.message]
    assert len(disappearance) == 1
    assert disappearance[0].path == "主角.name"
    assert disappearance[0].round_number == 2


# ── R3: type drift ─────────────────────────────────────────────────────

def test_r3_type_drift():
    rounds = [_round(1, 1), _round(2, 2)]
    snaps = [
        _snap(1, {"主角": {"hp": 10}}, ["主角.hp"]),
        _snap(2, {"主角": {"hp": "10"}}, ["主角.hp"]),
    ]
    logs = [
        _log(1, "主角.hp", op="=", status="applied", before=0, after=10),
        _log(2, "主角.hp", op="=", status="applied", before=10, after="10"),
    ]
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    drift = [f for f in findings if "类型漂移" in f.message]
    assert len(drift) == 1
    assert drift[0].path == "主角.hp"
    assert "int" in drift[0].message and "str" in drift[0].message


# ── R4: untracked change ───────────────────────────────────────────────

def test_r4_untracked_change():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"主角": {"hp": 99}}, ["主角.hp"])]
    logs = []  # no command explains the change
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    untracked = [f for f in findings if "没有任何日志命令" in f.message]
    assert len(untracked) == 1
    assert untracked[0].level == ErrorLevel.LV3


def test_r4_tracked_change_not_reported():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"主角": {"hp": 99}}, ["主角.hp"])]
    logs = [_log(1, "主角.hp", op="=", status="applied")]
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    untracked = [f for f in findings if "没有任何日志命令" in f.message]
    assert untracked == []


# ── ordering & stability ───────────────────────────────────────────────

def test_findings_sorted_by_round():
    rounds = [_round(1, 1), _round(2, 2)]
    snaps = [
        _snap(1, {"a": 1}, ["a"]),
        _snap(2, {"a": 1}, ["b"]),
    ]
    logs = []  # both rounds have untracked changes
    findings = DynamicLocator().analyze(rounds, snaps, logs)
    assert len(findings) == 2  # round1: untracked "a"; round2: untracked "b"
    round_nos = [f.round_number for f in findings]
    assert round_nos == [1, 2]


def test_empty_inputs_produce_no_findings():
    assert DynamicLocator().analyze([], [], []) == []


def test_analyze_is_repeatable():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"x": 1}, ["x"])]
    logs = []
    locator = DynamicLocator()
    first = locator.analyze(rounds, snaps, logs)
    second = locator.analyze(rounds, snaps, logs)
    assert [f.error_id for f in first] == [f.error_id for f in second]
    assert [f.message for f in first] == [f.message for f in second]


def test_finding_to_dict_shape():
    rounds = [_round(1, 1)]
    snaps = [_snap(1, {"x": 1}, ["x"])]
    logs = []
    f = DynamicLocator().analyze(rounds, snaps, logs)[0]
    d = f.to_dict()
    assert d["category"] == "动态"
    assert d["is_static"] == 0
    assert d["error_id"].startswith("DYN-")
    assert "round_number" in d and d["round_number"] == 1
