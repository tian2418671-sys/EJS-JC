"""Static checker — MVU command validation + schema linkage + initvar checks.

Phase 2 core module. Three categories of static checks:
  1. MVU command format & path validation (category=MVU)
  2. EJS variable ↔ Schema linkage (category=联动)
  3. initvar block completeness & type consistency (category=MVU)

When schema.json is unavailable, linkage and initvar checks are skipped
(degraded mode); MVU command format validation still runs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ..core.ejs_parser import EJSVariableReference
from ..core.schema_loader import SchemaInfo
from ..models.check_result import CheckResult, ErrorCategory, ErrorLevel


@dataclass
class MVUCommand:
    """A parsed MVU update command from an HTML comment."""
    raw: str
    path: str
    operator: str       # "=", "+=", "-="
    value: str
    line: int
    is_valid: bool
    note: Optional[str] = None

    @property
    def value_type(self) -> str:
        """Inferred type of the value: string / number / boolean."""
        v = self.value.strip()
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            return "string"
        if v.lower() in ("true", "false"):
            return "boolean"
        try:
            float(v)
            return "number"
        except ValueError:
            return "string"  # fallback: treat unquoted non-numeric as string


# ── Regex patterns ──────────────────────────────────────────────────

# <!-- mvu: path op value -->  (case-insensitive mvu)
_MVU_CMD_RE = re.compile(
    r"<!--\s*[Mm][Vv][Uu]\s*:\s*(.+?)\s*-->", re.DOTALL
)

# Parse "path operator value" from command content
_MVU_PARSE_RE = re.compile(r"^(.+?)\s*(\+=|-=|=)\s*(.+)$")

# Valid variable path (supports Chinese, word chars, numeric indices)
_VALID_PATH_RE = re.compile(
    r"^[\w\u4e00-\u9fff]+(?:\[\d+\])?(?:\.[\w\u4e00-\u9fff]+(?:\[\d+\])?)*$"
)

# initvar block finder: const/var/let/ nothing  initvar  =/:  { ... }
_INITVAR_RE = re.compile(r"(?:const|var|let)?\s*initvar\s*[=:]\s*")


class StaticChecker:
    """Static check orchestrator for MVU commands, linkage, and initvar."""

    def __init__(self):
        self._file_path: str = ""
        self._mvu_counter: int = 0
        self._link_counter: int = 0

    # ── Public API ──────────────────────────────────────────────────

    def check_mvu_commands(
        self,
        content: str,
        file_path: str = "",
        schema_info: Optional[SchemaInfo] = None,
    ) -> List[CheckResult]:
        """Check MVU update commands for format and path validity."""
        self._file_path = file_path
        self._mvu_counter = 0

        results: List[CheckResult] = []
        commands = self._extract_mvu_commands(content)

        schema_paths = schema_info.get_path_set() if schema_info else None
        schema_types = schema_info.get_path_types() if schema_info else None
        has_schema = schema_paths is not None and len(schema_paths) > 0

        for cmd in commands:
            if not cmd.is_valid:
                results.append(self._make_mvu_result(
                    level=ErrorLevel.LV2,
                    message=f"第 {cmd.line} 行：MVU 命令格式错误：{cmd.note}",
                    line=cmd.line,
                    path=cmd.path or None,
                    suggestion="按标准格式重写：<!-- mvu: 路径 操作符 值 -->",
                ))
                continue

            if has_schema:
                matched = self._match_schema_path(cmd.path, schema_paths)
                if matched is None:
                    results.append(self._make_mvu_result(
                        level=ErrorLevel.LV3,
                        message=(
                            f"第 {cmd.line} 行：MVU 命令路径「{cmd.path}」"
                            f"在 Schema 中不存在"
                        ),
                        line=cmd.line,
                        path=cmd.path,
                        suggestion=f"检查路径拼写或在 Schema 中添加「{cmd.path}」",
                    ))
                elif schema_types:
                    expected = schema_types.get(matched, "any")
                    # Container check: can't assign to object/array
                    if expected in ("object", "array"):
                        results.append(self._make_mvu_result(
                            level=ErrorLevel.LV3,
                            message=(
                                f"第 {cmd.line} 行：路径「{cmd.path}」是 "
                                f"{expected} 类型，不能直接赋值"
                            ),
                            line=cmd.line,
                            path=cmd.path,
                            suggestion="改为赋值到叶子节点路径",
                        ))
                    elif not self._type_compatible(
                        expected, cmd.value_type, cmd.operator
                    ):
                        results.append(self._make_mvu_result(
                            level=ErrorLevel.LV3,
                            message=(
                                f"第 {cmd.line} 行：类型不匹配 — "
                                f"路径「{cmd.path}」期望 {expected}，"
                                f"但值为 {cmd.value_type}"
                            ),
                            line=cmd.line,
                            path=cmd.path,
                            suggestion=f"将值改为 {expected} 类型",
                        ))

        return results

    def check_linkage(
        self,
        var_refs: List[EJSVariableReference],
        file_path: str = "",
        schema_info: Optional[SchemaInfo] = None,
    ) -> List[CheckResult]:
        """Check EJS variable references against schema paths."""
        self._file_path = file_path
        self._link_counter = 0

        results: List[CheckResult] = []
        if schema_info is None:
            return results  # degraded mode — skip linkage

        schema_paths = schema_info.get_path_set()
        if not schema_paths:
            return results

        for ref in var_refs:
            if not ref.is_static or ref.path is None:
                continue
            matched = self._match_schema_path(ref.path, schema_paths)
            if matched is None:
                results.append(self._make_link_result(
                    level=ErrorLevel.LV2,
                    message=(
                        f"第 {ref.line} 行：EJS 变量路径「{ref.path}」"
                        f"在 Schema 中不存在"
                    ),
                    line=ref.line,
                    path=ref.path,
                    suggestion=f"检查路径拼写或在 Schema 中添加「{ref.path}」",
                ))

        return results

    def check_initvar(
        self,
        content: str,
        file_path: str = "",
        schema_info: Optional[SchemaInfo] = None,
    ) -> List[CheckResult]:
        """Check initvar block completeness and type consistency."""
        self._file_path = file_path
        # Note: does NOT reset _mvu_counter (continues numbering)

        results: List[CheckResult] = []
        if schema_info is None:
            return results

        schema_paths = schema_info.get_path_set()
        if not schema_paths:
            return results

        initvar_data = self._extract_initvar(content)
        if initvar_data is None:
            return results

        initvar_path_types = self._flatten_paths(initvar_data)
        initvar_paths = set(initvar_path_types.keys())

        schema_leaves = schema_info.get_leaf_paths()
        schema_types = schema_info.get_path_types()

        # 1. Missing fields: schema leaves not in initvar
        for leaf in schema_leaves:
            if self._match_schema_path(leaf, initvar_paths) is None:
                results.append(self._make_mvu_result(
                    level=ErrorLevel.LV2,
                    message=f"initvar 缺少 Schema 必填字段「{leaf}」",
                    path=leaf,
                    suggestion=f"在 initvar 中补充「{leaf}」的初始值",
                    auto_fixable=True,
                ))

        # 2. Type mismatches: initvar leaves vs schema types
        initvar_leaves = {
            p: t for p, t in initvar_path_types.items()
            if t not in ("object", "array")
        }
        for path, actual_type in initvar_leaves.items():
            matched = self._match_schema_path(path, schema_paths)
            if matched:
                expected = schema_types.get(matched, "any")
                if expected != "any" and not self._type_compatible(
                    expected, actual_type, "="
                ):
                    results.append(self._make_mvu_result(
                        level=ErrorLevel.LV2,
                        message=(
                            f"initvar 类型不匹配 — 路径「{path}」"
                            f"期望 {expected}，但值为 {actual_type}"
                        ),
                        path=path,
                        suggestion=f"将 initvar 中「{path}」的值改为 "
                                   f"{expected} 类型",
                    ))

        # 3. Extra fields: initvar paths not in schema (Lv.3 warning)
        for path in initvar_leaves:
            if self._match_schema_path(path, schema_paths) is None:
                results.append(self._make_mvu_result(
                    level=ErrorLevel.LV3,
                    message=f"initvar 字段「{path}」在 Schema 中未定义",
                    path=path,
                    suggestion=f"从 initvar 中删除「{path}」或在 Schema "
                               f"中添加该路径",
                ))

        return results

    # ── MVU command extraction ──────────────────────────────────────

    def _extract_mvu_commands(self, content: str) -> List[MVUCommand]:
        """Extract and validate MVU commands from content."""
        commands: List[MVUCommand] = []
        for match in _MVU_CMD_RE.finditer(content):
            raw = match.group(0)
            inner = match.group(1).strip()
            line = content[: match.start()].count("\n") + 1

            m = _MVU_PARSE_RE.match(inner)
            if not m:
                commands.append(MVUCommand(
                    raw=raw, path="", operator="", value="",
                    line=line, is_valid=False, note="缺少操作符或值",
                ))
                continue

            path_raw = m.group(1).strip()
            operator = m.group(2)
            value = m.group(3).strip()

            if not path_raw:
                commands.append(MVUCommand(
                    raw=raw, path="", operator=operator, value=value,
                    line=line, is_valid=False, note="缺少变量路径",
                ))
                continue

            norm_path = re.sub(r"\[(\d+)\]", r".\1", path_raw)

            if not _VALID_PATH_RE.match(path_raw):
                commands.append(MVUCommand(
                    raw=raw, path=norm_path, operator=operator, value=value,
                    line=line, is_valid=False,
                    note=f"路径格式无效：{path_raw}",
                ))
                continue

            if not value:
                commands.append(MVUCommand(
                    raw=raw, path=norm_path, operator=operator, value="",
                    line=line, is_valid=False, note="缺少值",
                ))
                continue

            commands.append(MVUCommand(
                raw=raw, path=norm_path, operator=operator, value=value,
                line=line, is_valid=True,
            ))

        return commands

    # ── initvar extraction ──────────────────────────────────────────

    def _extract_initvar(self, content: str) -> Optional[dict]:
        """Find and parse the initvar block from content."""
        match = _INITVAR_RE.search(content)
        if not match:
            return None

        pos = match.end()
        # Find opening brace
        while pos < len(content) and content[pos] != "{":
            pos += 1
        if pos >= len(content):
            return None

        # Match braces (respecting string literals)
        depth = 0
        start = pos
        in_string = False
        string_char: Optional[str] = None
        while pos < len(content):
            ch = content[pos]
            if in_string:
                if ch == "\\":
                    pos += 1  # skip escaped char
                elif ch == string_char:
                    in_string = False
            else:
                if ch in "\"'":
                    in_string = True
                    string_char = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
            pos += 1

        if depth != 0:
            return None

        block = content[start : pos + 1]

        # Try JSON parse first
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass

        # Try fixing common JS object literal issues
        try:
            fixed = self._fix_js_object(block)
            return json.loads(fixed)
        except (json.JSONDecodeError, Exception):
            pass

        return None

    @staticmethod
    def _fix_js_object(text: str) -> str:
        """Fix common JS object literal issues for JSON parsing."""
        # Quote unquoted keys: { key: → { "key":
        fixed = re.sub(
            r'([{,]\s*)([\w\u4e00-\u9fff]+)(\s*:)',
            r'\1"\2"\3',
            text,
        )
        # Single quotes → double quotes
        fixed = fixed.replace("'", '"')
        # Remove trailing commas before } or ]
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        return fixed

    # ── Path matching ───────────────────────────────────────────────

    @staticmethod
    def _match_schema_path(
        path: str, schema_paths: Set[str]
    ) -> Optional[str]:
        """Match a variable path against schema paths.

        Handles numeric index → * wildcard normalization.
        Returns the matched schema path, or None.
        """
        if path in schema_paths:
            return path

        # Replace numeric segments with *
        parts = path.split(".")
        wildcarded = False
        for i, part in enumerate(parts):
            if part.isdigit():
                parts[i] = "*"
                wildcarded = True
        if wildcarded:
            wp = ".".join(parts)
            if wp in schema_paths:
                return wp

        return None

    # ── Type checking ───────────────────────────────────────────────

    @staticmethod
    def _type_compatible(expected: str, actual: str, operator: str) -> bool:
        """Check if actual type is compatible with expected type."""
        if expected == "any" or actual == "any":
            return True
        # += and -= require number on both sides
        if operator in ("+=", "-="):
            return expected == "number" and actual == "number"
        # = : normalize and compare
        norm = {"integer": "number", "float": "number"}
        return norm.get(expected, expected) == norm.get(actual, actual)

    # ── Path flattening ─────────────────────────────────────────────

    def _flatten_paths(self, data, prefix: str = "") -> Dict[str, str]:
        """Flatten nested dict/list into {path: type} mapping."""
        result: Dict[str, str] = {}
        if isinstance(data, dict):
            for key, val in data.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(val, bool):
                    result[path] = "boolean"
                elif isinstance(val, (int, float)):
                    result[path] = "number"
                elif isinstance(val, str):
                    result[path] = "string"
                elif isinstance(val, dict):
                    result[path] = "object"
                    result.update(self._flatten_paths(val, path))
                elif isinstance(val, list):
                    result[path] = "array"
                    if val and isinstance(val[0], dict):
                        result.update(
                            self._flatten_paths(val[0], f"{path}.*")
                        )
                elif val is None:
                    result[path] = "null"
                else:
                    result[path] = "any"
        return result

    # ── Result helpers ──────────────────────────────────────────────

    def _make_mvu_result(
        self,
        level: ErrorLevel,
        message: str,
        line: Optional[int] = None,
        path: Optional[str] = None,
        suggestion: Optional[str] = None,
        auto_fixable: bool = False,
    ) -> CheckResult:
        self._mvu_counter += 1
        return CheckResult(
            error_id=f"MVU-{self._mvu_counter:04d}",
            level=level,
            category=ErrorCategory.MVU,
            file_path=self._file_path,
            message=message,
            line_number=line,
            path=path,
            suggestion=suggestion,
            auto_fixable=auto_fixable,
            status="pending",
            is_static=True,
        )

    def _make_link_result(
        self,
        level: ErrorLevel,
        message: str,
        line: Optional[int] = None,
        path: Optional[str] = None,
        suggestion: Optional[str] = None,
        auto_fixable: bool = False,
    ) -> CheckResult:
        self._link_counter += 1
        return CheckResult(
            error_id=f"LINK-{self._link_counter:04d}",
            level=level,
            category=ErrorCategory.LINKAGE,
            file_path=self._file_path,
            message=message,
            line_number=line,
            path=path,
            suggestion=suggestion,
            auto_fixable=auto_fixable,
            status="pending",
            is_static=True,
        )
