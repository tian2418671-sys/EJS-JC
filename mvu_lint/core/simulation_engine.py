"""Rule-driven simulation engine (Phase 3 / F4 — technical validation).

A deterministic, LLM-free stand-in for the AI dialogue loop.  It advances a
character card's variable state by *re-evaluating worldbook activation
conditions* against the current variables and applying the concrete MVU
commands embedded in the activated entries:

  * ``<!-- mvu: path op value -->`` comments (``=`` / ``+=`` / ``-=``)
  * ``<UpdateVariable>`` blocks carrying RFC 6902 ``<JSONPatch>`` arrays

Because variable changes can flip ``@@if getvar(...)`` conditions, running the
engine repeatedly *derives* the next plot beat from initvar changes — exactly
the "基于 initvar 值变更推导后续剧情" behavior required of Phase 3.  No LLM is
involved; the UI labels this "技术验证" (technical validation).  Phase 5 swaps
in a real model that *emits* these commands, leaving this apply/snapshot/log
pipeline intact.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.json_patch import (
    extract_json_patch_blocks,
    extract_update_variable_blocks,
    is_template_text,
    json_pointer_to_segments,
    parse_json_patch,
)

# ── MVU comment command ──────────────────────────────────────────────

_MVU_CMD_RE = re.compile(
    r"<!--\s*[Mm][Vv][Uu]\s*:\s*(.+?)\s*-->", re.DOTALL
)
_MVU_PARSE_RE = re.compile(r"^(.+?)\s*(\+=|-=|=)\s*(.+)$")

# ── Condition parsing ────────────────────────────────────────────────

# getvar('path'[, {defaults: VALUE}])
_GETVAR_RE = re.compile(
    r"getvar\(\s*(['\"])([^'\"]+)\1\s*"
    r"(?:,\s*\{\s*defaults?\s*:\s*([^}]*)\s*\})?\s*\)"
)
_IF_PREFIX_RE = re.compile(r"^@@if\s*", re.IGNORECASE)
_INCLUDES_RE = re.compile(r"^(.*?)\.includes\(\s*(['\"])([^'\"]*)\2\s*\)\s*$")
_COMPARE_OPS = ("===", "!==", "==", "!=", ">=", "<=", ">", "<")


@dataclass
class CommandExecution:
    """One applied (or failed) MVU command, serializable for the command log."""
    file_path: str
    command_type: str        # "mvu" | "json_patch"
    path: str
    op: str                  # "=", "+=", "-=", "add", "replace", "remove", "move"
    value: Any = None
    before: Any = None
    after: Any = None
    status: str = "applied"  # "applied" | "error"
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "command_type": self.command_type,
            "path": self.path,
            "op": self.op,
            "value": self.value,
            "before": self.before,
            "after": self.after,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class StepResult:
    """The outcome of one simulation step."""
    round_number: int
    user_input: str
    activated_entries: List[str] = field(default_factory=list)
    commands: List[CommandExecution] = field(default_factory=list)
    changed_paths: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "user_input": self.user_input,
            "activated_entries": self.activated_entries,
            "commands": [c.to_dict() for c in self.commands],
            "changed_paths": self.changed_paths,
            "errors": self.errors,
            "warnings": self.warnings,
            "snapshot": self.snapshot,
        }


# ── Value coercion ───────────────────────────────────────────────────

def _coerce_value(text: str) -> Any:
    """Convert an MVU comment scalar to bool / number / string."""
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t


def _flatten(data: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Flatten a nested dict/list to dotted leaf paths (lists keep indices)."""
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


# ── Variable state ───────────────────────────────────────────────────

class VariableState:
    """A dict-backed variable store with dotted / JSON-Pointer path access.

    Supports RFC 6902 add/replace/remove/move and the ``=`` / ``+=`` / ``-=``
    operators used by ``<!-- mvu: -->`` comments.
    """

    def __init__(self, initial: Optional[dict] = None):
        self._data: Any = copy.deepcopy(initial or {})

    # ── path helpers ────────────────────────────────────────────────

    @staticmethod
    def _to_segments(path: str) -> Optional[List[str]]:
        if not path:
            return []
        if path.startswith("/"):
            return json_pointer_to_segments(path)
        norm = re.sub(r"\[(\d+)\]", r".\1", path)
        return [seg for seg in norm.split(".") if seg != ""]

    @staticmethod
    def _resolve_child(node: Any, seg: str) -> Any:
        if isinstance(node, dict):
            return node.get(seg)
        if isinstance(node, list) and str(seg).isdigit():
            i = int(seg)
            return node[i] if 0 <= i < len(node) else None
        return None

    def get(self, path: str, default: Any = None) -> Any:
        segments = self._to_segments(path)
        if segments is None:
            return default
        node = self._data
        for seg in segments:
            node = self._resolve_child(node, seg)
            if node is None:
                return default
        return node

    def snapshot(self) -> Any:
        return copy.deepcopy(self._data)

    # ── mutation ────────────────────────────────────────────────────

    def _apply_add(self, segments: List[str], value: Any) -> bool:
        if not segments:
            self._data = copy.deepcopy(value)
            return True
        parent, last = segments[:-1], segments[-1]
        node = self._data
        for seg in parent:
            node = self._resolve_child(node, seg)
            if node is None:
                return False
        if isinstance(node, list):
            if last == "-":
                node.append(copy.deepcopy(value))
                return True
            try:
                idx = int(last)
            except ValueError:
                return False
            if idx < 0 or idx > len(node):
                return False
            node.insert(idx, copy.deepcopy(value))
            return True
        if isinstance(node, dict):
            node[last] = copy.deepcopy(value)
            return True
        return False

    def _apply_replace(self, segments: List[str], value: Any) -> bool:
        node = self.get("/".join([""] + segments) if segments else "")
        if segments is None or node is None:
            return False
        # Navigate to parent and assign the final key/index.
        parent, last = segments[:-1], segments[-1]
        target = self._data
        for seg in parent:
            target = self._resolve_child(target, seg)
            if target is None:
                return False
        if isinstance(target, dict):
            if last not in target:
                return False
            target[last] = copy.deepcopy(value)
            return True
        if isinstance(target, list) and str(last).isdigit():
            i = int(last)
            if 0 <= i < len(target):
                target[i] = copy.deepcopy(value)
                return True
        return False

    def _apply_remove(self, segments: List[str]) -> bool:
        if not segments:
            self._data = {}
            return True
        parent, last = segments[:-1], segments[-1]
        node = self._data
        for seg in parent:
            node = self._resolve_child(node, seg)
            if node is None:
                return False
        if isinstance(node, dict):
            return node.pop(last, None) is not None
        if isinstance(node, list) and str(last).isdigit():
            i = int(last)
            if 0 <= i < len(node):
                node.pop(i)
                return True
        return False

    def apply_json_patch(self, ops: List[Any]) -> List[tuple]:
        """Apply a list of JSONPatchOp objects.

        Returns a list of (op, ok, error) tuples for per-op logging.
        """
        outcomes: List[tuple] = []
        for op in ops:
            segments = json_pointer_to_segments(op.path)
            if segments is None:
                outcomes.append((op, False, f"非法 JSON Pointer: {op.path}"))
                continue
            if op.op == "add":
                ok = self._apply_add(segments, op.value)
            elif op.op == "replace":
                ok = self._apply_replace(segments, op.value)
            elif op.op == "remove":
                ok = self._apply_remove(segments)
            elif op.op == "move":
                from_seg = json_pointer_to_segments(op.from_ or "")
                if from_seg is None:
                    outcomes.append((op, False, f"move 的 from 非法: {op.from_}"))
                    continue
                value = self.get("/".join([""] + from_seg))
                if value is None and not self._contains(from_seg):
                    outcomes.append((op, False, f"move 的 from 不存在: {op.from_}"))
                    continue
                self._apply_remove(from_seg)
                ok = self._apply_add(segments, value)
            else:
                outcomes.append((op, False, f"不支持的 op: {op.op}"))
                continue
            outcomes.append((op, ok, "" if ok else f"应用失败: {op.path}"))
        return outcomes

    def _contains(self, segments: List[str]) -> bool:
        node = self._data
        for seg in segments:
            nxt = self._resolve_child(node, seg)
            if nxt is None:
                return False
            node = nxt
        return True

    def apply_mvu_comment(self, path: str, operator: str, value: Any) -> bool:
        """Apply ``=`` / ``+=`` / ``-=`` to a dotted path."""
        if operator == "=":
            segments = self._to_segments(path)
            if segments is None:
                return False
            return self._apply_add(segments, value)

        current = self.get(path)
        if operator == "+=":
            if isinstance(current, (int, float)) and isinstance(value, (int, float)):
                new = current + value
            elif isinstance(current, str) and isinstance(value, str):
                new = current + value
            else:
                return False
        elif operator == "-=":
            if not (isinstance(current, (int, float)) and isinstance(value, (int, float))):
                return False
            new = current - value
        else:
            return False
        return self.apply_mvu_comment(path, "=", new)


# ── Condition evaluator ──────────────────────────────────────────────

def _strip_var_prefix(path: str) -> str:
    for prefix in ("stat_data.", "data.", "locals."):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


class SimulationEngine:
    """Deterministic rule-driven dialogue simulator."""

    def __init__(self, entries: List[dict], initial_state: Optional[dict] = None):
        """Args:
            entries: list of {"file_path": str, "content": str} worldbook blocks.
            initial_state: initvar data-shape dict (variable initial values).
        """
        self.entries = entries
        self.state = VariableState(initial_state)
        self.round_number = 0
        self._previous_flat: Dict[str, Any] = _flatten(self.state.snapshot())

    # ── condition evaluation ────────────────────────────────────────

    @staticmethod
    def _extract_conditions(content: str) -> List[str]:
        conds: List[str] = []
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("@@if"):
                expr = s[len("@@if"):].strip()
                expr = expr.split(" ---")[0].strip()
                if expr:
                    conds.append(expr)
        return conds

    def _resolve_getvar(self, expr: str) -> Any:
        m = _GETVAR_RE.search(expr)
        if not m:
            return expr
        path = _strip_var_prefix(m.group(2))
        default: Any = None
        if m.group(3) is not None:
            default = _coerce_value(m.group(3).strip())
        return self.state.get(path, default)

    @staticmethod
    def _compare(lhs: Any, rhs: Any, op: str) -> bool:
        if op in ("===", "=="):
            return lhs == rhs
        if op in ("!==", "!="):
            return lhs != rhs
        try:
            l, r = float(lhs), float(rhs)
        except (TypeError, ValueError):
            l, r = str(lhs), str(rhs)
        if op == ">":
            return l > r
        if op == "<":
            return l < r
        if op == ">=":
            return l >= r
        if op == "<=":
            return l <= r
        return False

    def _eval_condition(self, cond: str) -> bool:
        cond = _IF_PREFIX_RE.sub("", cond).strip()
        if not cond:
            return False
        if cond.startswith("!"):
            return not self._eval_condition(cond[1:].strip())

        m = _INCLUDES_RE.match(cond)
        if m:
            val = self._resolve_getvar(m.group(1))
            lit = m.group(3)
            if isinstance(val, str):
                return lit in val
            if isinstance(val, (list, tuple, set, dict)):
                return lit in val
            return False

        for op in _COMPARE_OPS:
            m = re.search(r"^(.*?)\s*" + re.escape(op) + r"\s*(.+)$", cond)
            if m:
                lhs = self._resolve_getvar(m.group(1))
                rhs = _coerce_value(m.group(2))
                return self._compare(lhs, rhs, op)

        # Bare getvar(...) → truthiness
        m = re.search(r"^getvar\((.*)\)$", cond)
        if m:
            return bool(self._resolve_getvar(cond))
        return False

    def _entry_active(self, content: str, user_input: str) -> bool:
        """An entry activates when any @@if condition holds (OR semantics).

        Entries without conditions are always-on lore; if the caller supplied a
        user input, it may additionally keyword-trigger an entry.
        """
        conds = self._extract_conditions(content)
        if conds:
            return any(self._eval_condition(c) for c in conds)
        if user_input and user_input.strip() and user_input.strip() in content:
            return True
        return True  # no conditions → constant/lore entry

    # ── command extraction ──────────────────────────────────────────

    @staticmethod
    def _extract_mvu_comments(content: str) -> List[tuple]:
        """Return list of (path, operator, coerced_value, raw, line)."""
        out: List[tuple] = []
        for match in _MVU_CMD_RE.finditer(content):
            inner = match.group(1).strip()
            m = _MVU_PARSE_RE.match(inner)
            if not m:
                continue
            path = re.sub(r"\[(\d+)\]", r".\1", m.group(1).strip())
            op = m.group(2)
            value = _coerce_value(m.group(3))
            out.append((path, op, value, match.group(0)))
        return out

    def _apply_commands(self, file_path: str, content: str,
                        commands: List[CommandExecution],
                        errors: List[str], warnings: List[str]) -> None:
        # 1. <!-- mvu: --> comments
        for path, op, value, raw in self._extract_mvu_comments(content):
            before = self.state.get(path)
            ok = self.state.apply_mvu_comment(path, op, value)
            after = self.state.get(path)
            commands.append(CommandExecution(
                file_path=file_path, command_type="mvu", path=path, op=op,
                value=value, before=before, after=after,
                status="applied" if ok else "error",
                error="" if ok else f"命令执行失败: {raw.strip()}",
            ))
            if not ok:
                errors.append(f"{file_path}: 命令执行失败: {raw.strip()}")

        # 2. <UpdateVariable> JSON Patch blocks
        blocks, unclosed = extract_update_variable_blocks(content)
        for _s, _e in unclosed:
            warnings.append(f"{file_path}: <UpdateVariable> 标签未闭合")
        for block in blocks:
            jp_blocks, jp_unclosed = extract_json_patch_blocks(block.inner, block.line)
            for _s, _e in jp_unclosed:
                warnings.append(f"{file_path}: <JSONPatch> 标签未闭合")
            for json_text, _line in jp_blocks:
                if is_template_text(json_text):
                    continue
                try:
                    ops = parse_json_patch(json_text, _line)
                except ValueError:
                    continue  # prose mention, not concrete data
                outcomes = self.state.apply_json_patch(ops)
                for op, ok, err in outcomes:
                    before = self.state.get(op.path) if op.path else None
                    commands.append(CommandExecution(
                        file_path=file_path, command_type="json_patch",
                        path=op.path, op=op.op, value=op.value,
                        before=before, after=self.state.get(op.path),
                        status="applied" if ok else "error", error=err,
                    ))
                    if not ok:
                        errors.append(f"{file_path}: {err}")

    # ── stepping ────────────────────────────────────────────────────

    def step(self, user_input: str = "") -> StepResult:
        """Advance one simulation step and return the outcome."""
        self.round_number += 1
        commands: List[CommandExecution] = []
        errors: List[str] = []
        warnings: List[str] = []
        activated: List[str] = []

        for entry in self.entries:
            file_path = entry.get("file_path", "")
            content = entry.get("content", "")
            if not self._entry_active(content, user_input):
                continue
            activated.append(file_path)
            self._apply_commands(file_path, content, commands, errors, warnings)

        before_flat = self._previous_flat
        snapshot = self.state.snapshot()
        after_flat = _flatten(snapshot)
        changed = sorted(
            p for p in set(before_flat) | set(after_flat)
            if before_flat.get(p) != after_flat.get(p)
        )
        self._previous_flat = after_flat

        return StepResult(
            round_number=self.round_number,
            user_input=user_input,
            activated_entries=activated,
            commands=commands,
            changed_paths=changed,
            errors=errors,
            warnings=warnings,
            snapshot=snapshot,
        )

    def run(self, max_steps: int = 20, user_inputs: Optional[List[str]] = None) -> List[StepResult]:
        """Run steps until the state stabilizes or ``max_steps`` is reached.

        When ``user_inputs`` is given, they are consumed one per step; otherwise
        the engine auto-wanders (re-evaluating conditions against new values).
        """
        results: List[StepResult] = []
        inputs = list(user_inputs or [])
        for _ in range(max_steps):
            ui = inputs.pop(0) if inputs else ""
            result = self.step(ui)
            results.append(result)
            if not result.changed_paths and not inputs:
                break
        return results

    def serialize_commands(self, results: List[StepResult]) -> str:
        """Serialize executed MVU commands to JSON (F5 log tracing)."""
        payload = [r.to_dict() for r in results]
        return json.dumps(payload, ensure_ascii=False, indent=2)
