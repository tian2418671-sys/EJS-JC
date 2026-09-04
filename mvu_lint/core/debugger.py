"""Dynamic locator (Phase 4 / F6) — locate abnormal variable-change points.

Consumes the persisted simulation artifacts (rounds, state snapshots and the
command log) and turns them into *dynamic findings*:

  * R1  command failures — a command that failed at runtime (bad path, bad op)
  * R2  variable disappearance — a variable that had a value and lost it
  * R3  type drift — the same path changes value type across two snapshots
  * R4  untracked change — a path changed but no logged command explains it

The locator is deliberately Qt-free so it is fully unit-testable headless
(see tests/test_debugger.py).  Findings carry the same ErrorLevel vocabulary
as static errors so the GUI can render them side by side with Phase 2 static
errors (dynamic + static report integration).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.check_result import ErrorLevel

# ── path normalization ──────────────────────────────────────────────────

_STAT_PREFIXES = ("stat_data.", "data.", "locals.")


def norm_path(path: str) -> str:
    """Normalize a logged command path to the flat dotted form used by snapshots.

    Handles both JSON Pointers (``/data/主角.好感度``) and dotted paths
    (``stat_data.主角.好感度``); ``[N]`` array accessors become ``.N``.
    """
    if not path:
        return ""
    p = path.strip()
    if p.startswith("/"):
        parts = []
        for token in p[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if token:
                parts.append(token)
        p = ".".join(parts)
    p = re.sub(r"\[(\d+)\]", r".\1", p)
    for prefix in _STAT_PREFIXES:
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    return p


def _flatten(data: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Flatten nested dict/list to dotted leaf paths (lists keep indices)."""
    if out is None:
        out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                _flatten(v, p, out)
            else:
                out[p] = v
    elif isinstance(data, list):
        for i, v in enumerate(data):
            p = f"{prefix}.{i}"
            if isinstance(v, (dict, list)):
                _flatten(v, p, out)
            else:
                out[p] = v
    else:
        out[prefix] = data
    return out


def _type_name(value: Any) -> str:
    if value is None:
        return "None"
    return type(value).__name__


# ── findings ────────────────────────────────────────────────────────────

@dataclass
class DynamicFinding:
    """One dynamic-locator finding, compatible with static-error rendering."""
    error_id: str
    level: ErrorLevel
    file_path: str
    message: str
    round_number: Optional[int] = None
    path: Optional[str] = None
    suggestion: Optional[str] = None
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "level": self.level.value,
            "category": "动态",
            "file_path": self.file_path,
            "line_number": None,
            "round_number": self.round_number,
            "path": self.path,
            "message": self.message,
            "suggestion": self.suggestion,
            "evidence": self.evidence,
            "status": "pending",
            "is_static": 0,
        }


# ── locator ─────────────────────────────────────────────────────────────

class DynamicLocator:
    """Analyze simulation artifacts and produce dynamic findings."""

    def __init__(self) -> None:
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"DYN-{self._seq:04d}"

    # ── public API ───────────────────────────────────────────────────

    def analyze(self,
                rounds: List[dict],
                snapshots: List[dict],
                logs: List[dict],
                initial_state: Optional[Dict[str, Any]] = None,
                ) -> List[DynamicFinding]:
        """Run all rules over persisted simulation data.

        Args:
            rounds: rows from simulation_rounds (DB dicts).
            snapshots: rows from state_snapshots (DB dicts, round_id linked).
            logs: rows from simulation_logs (DB dicts, round_id linked).
            initial_state: the card's initvar data-shape dict, used as the
                baseline for the first snapshot diff (round 0 → round 1).

        Returns a list of findings sorted by round then severity.
        """
        self._seq = 0
        findings: List[DynamicFinding] = []
        by_round: Dict[int, dict] = {}
        for r in rounds:
            by_round[r["id"]] = r

        logs_by_round: Dict[int, List[dict]] = {}
        for log in logs:
            logs_by_round.setdefault(log["round_id"], []).append(log)

        snap_by_round: Dict[int, dict] = {}
        for snap in snapshots:
            snap_by_round[snap["round_id"]] = snap

        # ordered round ids
        round_ids = [r["id"] for r in sorted(rounds, key=lambda x: x["round_number"])]

        self._check_command_failures(round_ids, logs_by_round, by_round, findings)
        self._check_snapshot_diffs(
            round_ids, snap_by_round, logs_by_round, by_round, findings,
            initial_state=initial_state,
        )

        # stable ordering: by round_number then id
        findings.sort(key=lambda f: (f.round_number or 0, f.error_id))
        return findings

    # ── R1: command failures ─────────────────────────────────────────

    def _check_command_failures(self, round_ids, logs_by_round, by_round, findings):
        for rid in round_ids:
            round_no = by_round[rid]["round_number"]
            for log in logs_by_round.get(rid, []):
                if log.get("status") != "error":
                    continue
                path = norm_path(log.get("path", ""))
                err = log.get("error") or "命令执行失败"
                findings.append(DynamicFinding(
                    error_id=self._next_id(),
                    level=ErrorLevel.LV2,
                    file_path=log.get("file_path", ""),
                    message=f"命令执行失败: {log.get('op', '')} {path} — {err}",
                    round_number=round_no,
                    path=path or None,
                    suggestion=(
                        "检查该路径是否在「# 变量初始值」中定义，"
                        "或修复命令引用的变量名/索引。"
                    ),
                    evidence=f"{log.get('op', '')} @ 回合 {round_no}",
                ))

    # ── R2/R3: snapshot diff analysis ────────────────────────────────

    def _check_snapshot_diffs(self, round_ids, snap_by_round, logs_by_round,
                              by_round, findings,
                              initial_state: Optional[Dict[str, Any]] = None):
        prev_flat: Dict[str, Any] = _flatten(initial_state or {})
        prev_round_no: Optional[int] = 0

        for rid in round_ids:
            snap = snap_by_round.get(rid)
            if snap is None:
                continue
            round_no = by_round[rid]["round_number"]
            try:
                data = json.loads(snap.get("stat_data") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            cur_flat = _flatten(data)
            changed_raw = snap.get("changed_paths") or "[]"
            try:
                changed = set(json.loads(changed_raw))
            except (json.JSONDecodeError, TypeError):
                changed = set()

            logged_paths = {
                norm_path(l.get("path", ""))
                for l in logs_by_round.get(rid, [])
            }

            if prev_flat:
                self._check_disappearance(
                    prev_flat, cur_flat, prev_round_no, round_no, findings
                )
                self._check_type_drift(
                    prev_flat, cur_flat, prev_round_no, round_no, findings
                )

            # R4: changed but no logged command (untracked mutation)
            for p in sorted(changed):
                if p not in logged_paths:
                    findings.append(DynamicFinding(
                        error_id=self._next_id(),
                        level=ErrorLevel.LV3,
                        file_path="",
                        message=f"变量「{p}」发生变化，但没有任何日志命令能解释该变更",
                        round_number=round_no,
                        path=p,
                        suggestion=(
                            "可能来自未解析的脚本标签（<%_ %> / 外部脚本）或模板文本，"
                            "请人工确认该轮变更来源。"
                        ),
                        evidence=f"changed_paths @ 回合 {round_no}",
                    ))

            prev_flat = cur_flat
            prev_round_no = round_no

    def _check_disappearance(self, prev_flat, cur_flat, prev_round_no,
                             round_no, findings):
        for p, old in prev_flat.items():
            if p not in cur_flat or cur_flat[p] is None:
                findings.append(DynamicFinding(
                    error_id=self._next_id(),
                    level=ErrorLevel.LV3,
                    file_path="",
                    message=f"变量「{p}」在回合 {round_no} 后丢失（原值: {old!r}）",
                    round_number=round_no,
                    path=p,
                    suggestion=(
                        "检查是否有 remove 命令或 +=/-= 把该变量清空；"
                        "如后续 EJS 仍引用它，将读取到 undefined。"
                    ),
                    evidence=f"回合 {prev_round_no} → {round_no}",
                ))

    def _check_type_drift(self, prev_flat, cur_flat, prev_round_no,
                          round_no, findings):
        for p, old in prev_flat.items():
            new = cur_flat.get(p)
            if new is None:
                continue
            if type(old) is type(new):
                continue
            findings.append(DynamicFinding(
                error_id=self._next_id(),
                level=ErrorLevel.LV3,
                file_path="",
                message=(
                    f"变量「{p}」类型漂移: {_type_name(old)} → {_type_name(new)} "
                    f"（回合 {prev_round_no} → {round_no}）"
                ),
                round_number=round_no,
                path=p,
                suggestion=(
                    "同一路径被以不同数据类型写入（如字符串 ↔ 数字），"
                    "可能造成 EJS 比较/算术运算失效，建议统一类型。"
                ),
                evidence=f"{old!r} → {new!r}",
            ))
