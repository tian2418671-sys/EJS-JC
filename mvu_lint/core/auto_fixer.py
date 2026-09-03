"""Auto-fixer — generates fix previews and applies automatic fixes.

Supports:
  - EJS unclosed tag: append %> at end of content
  - initvar missing field: add field with default value to initvar block
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..core.schema_loader import SchemaInfo


# initvar block finder (same pattern as static_checker)
_INITVAR_RE = re.compile(r"(?:const|var|let)?\s*initvar\s*[=:]\s*")


class AutoFixer:
    """Generate fix previews and apply automatic fixes."""

    def __init__(self, schema_info: Optional[SchemaInfo] = None):
        self._schema_info = schema_info
        self._schema_types = (
            schema_info.get_path_types() if schema_info else {}
        )
        self._schema_paths = (
            schema_info.get_path_set() if schema_info else set()
        )

    # ── Public API ──────────────────────────────────────────────────

    def generate_preview(
        self, error: dict, content: str
    ) -> Optional[str]:
        """Generate a human-readable fix preview.

        Args:
            error: Error dict from DB.
            content: Current file content.

        Returns:
            Preview text, or None if not auto-fixable.
        """
        if not error.get("auto_fixable"):
            return None

        category = error.get("category", "")
        message = error.get("message", "")
        path = error.get("path", "")
        line = error.get("line_number")

        if category == "EJS" and "未闭合" in message:
            return self._preview_unclosed_tag(content, line or 0)

        if category == "MVU" and "initvar 缺少" in message:
            return self._preview_initvar_missing(content, path)

        return None

    def apply_fix(
        self, error: dict, content: str
    ) -> Optional[str]:
        """Apply the fix and return the new content.

        Returns:
            Fixed content string, or None if not fixable.
        """
        if not error.get("auto_fixable"):
            return None

        category = error.get("category", "")
        message = error.get("message", "")
        path = error.get("path", "")
        line = error.get("line_number")

        if category == "EJS" and "未闭合" in message:
            return self._fix_unclosed_tag(content)

        if category == "MVU" and "initvar 缺少" in message:
            return self._fix_initvar_missing(content, path)

        return None

    # ── EJS unclosed tag ────────────────────────────────────────────

    @staticmethod
    def _preview_unclosed_tag(content: str, line: int) -> str:
        """Generate preview for unclosed EJS tag."""
        lines = content.split("\n")
        if 0 < line <= len(lines):
            original = lines[line - 1].rstrip()
        else:
            original = "(无法定位行)"
        return (
            f"修复预览 — EJS 标签未闭合\n"
            f"───────────────────────────\n"
            f"原文（第 {line} 行）:\n  {original}\n\n"
            f"修复方式：在文件末尾添加 %> 闭合标签"
        )

    @staticmethod
    def _fix_unclosed_tag(content: str) -> str:
        """Append %> at the end of content to close unclosed tags."""
        stripped = content.rstrip()
        if stripped.endswith("%>"):
            return content  # already closed (shouldn't happen)
        return stripped + "\n%>\n"

    # ── initvar missing field ───────────────────────────────────────

    def _preview_initvar_missing(
        self, content: str, path: str
    ) -> str:
        """Generate preview for missing initvar field."""
        default = self._default_value_for_path(path)
        return (
            f"修复预览 — initvar 缺少字段\n"
            f"───────────────────────────\n"
            f"缺失路径：{path}\n"
            f"默认值：{json.dumps(default, ensure_ascii=False)}\n\n"
            f"修复方式：在 initvar 块中添加该字段"
        )

    def _fix_initvar_missing(
        self, content: str, path: str
    ) -> Optional[str]:
        """Add a missing field to the initvar block."""
        block_start, block_end, block_text = self._find_initvar_block(content)
        if block_text is None:
            return None

        # Parse the block
        data = self._parse_block(block_text)
        if data is None or not isinstance(data, dict):
            return None

        # Set the missing path
        default = self._default_value_for_path(path)
        self._set_nested_path(data, path, default)

        # Serialize back
        new_block = json.dumps(data, ensure_ascii=False, indent=2)

        # Replace old block with new one
        return (
            content[:block_start]
            + new_block
            + content[block_end:]
        )

    # ── initvar block helpers ───────────────────────────────────────

    @staticmethod
    def _find_initvar_block(
        content: str
    ) -> tuple[int, int, Optional[str]]:
        """Find initvar block boundaries.

        Returns (start_index, end_index, block_text) or
        (0, 0, None) if not found.
        """
        match = _INITVAR_RE.search(content)
        if not match:
            return (0, 0, None)

        pos = match.end()
        # Find opening brace
        while pos < len(content) and content[pos] != "{":
            pos += 1
        if pos >= len(content):
            return (0, 0, None)

        # Match braces (respecting string literals)
        depth = 0
        start = pos
        in_string = False
        string_char: Optional[str] = None
        while pos < len(content):
            ch = content[pos]
            if in_string:
                if ch == "\\":
                    pos += 1
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
            return (0, 0, None)

        block = content[start : pos + 1]
        return (start, pos + 1, block)

    @staticmethod
    def _parse_block(block_text: str) -> Optional[dict]:
        """Parse a JS object literal block into a dict."""
        # Try JSON parse first
        try:
            return json.loads(block_text)
        except json.JSONDecodeError:
            pass

        # Try fixing common JS object literal issues
        try:
            fixed = re.sub(
                r'([{,]\s*)([\w\u4e00-\u9fff]+)(\s*:)',
                r'\1"\2"\3',
                block_text,
            )
            fixed = fixed.replace("'", '"')
            fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
            return json.loads(fixed)
        except (json.JSONDecodeError, Exception):
            return None

    # ── Default value helpers ───────────────────────────────────────

    def _default_value_for_path(self, path: str) -> Any:
        """Return a default value for a given path based on schema type."""
        if self._schema_info:
            matched = self._match_schema_path(
                path, self._schema_paths
            )
            if matched:
                expected_type = self._schema_types.get(matched, "string")
                return self._default_for_type(expected_type)
        return ""

    @staticmethod
    def _default_for_type(type_name: str) -> Any:
        """Return a default value for a schema type."""
        defaults = {
            "string": "",
            "number": 0,
            "integer": 0,
            "boolean": False,
            "object": {},
            "array": [],
            "null": None,
        }
        return defaults.get(type_name, "")

    @staticmethod
    def _match_schema_path(
        path: str, schema_paths: set
    ) -> Optional[str]:
        """Match a variable path against schema paths."""
        if path in schema_paths:
            return path
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

    @staticmethod
    def _set_nested_path(data: dict, path: str, value: Any) -> None:
        """Set a nested path in a dict, creating intermediate objects."""
        parts = path.split(".")
        current = data
        for i, part in enumerate(parts):
            if part == "*":
                return  # can't set wildcard path
            if i == len(parts) - 1:
                current[part] = value
            else:
                if part not in current or not isinstance(
                    current[part], dict
                ):
                    current[part] = {}
                current = current[part]
