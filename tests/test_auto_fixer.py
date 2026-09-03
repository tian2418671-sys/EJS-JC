"""Unit tests for AutoFixer — fix preview generation and fix application."""
from __future__ import annotations

import json
import re

from mvu_lint.core.auto_fixer import AutoFixer
from mvu_lint.core.schema_loader import SchemaLoader


def _make_schema_info():
    loader = SchemaLoader()
    return loader.load_from_dict({
        "主角": {
            "好感度": 50,
            "状态": "高兴",
            "物品栏": [
                {"名称": "剑", "数量": 1}
            ]
        }
    })


SIMPLE_SCHEMA = _make_schema_info()


# ── EJS unclosed tag fix ────────────────────────────────────────────

def test_fix_preview_unclosed_tag():
    """Preview for unclosed EJS tag should mention adding %>."""
    fixer = AutoFixer()
    content = "<%= data.x %>\n<% if (true) { \n"
    error = {
        "category": "EJS",
        "message": "第 2 行：EJS 标签未闭合，缺少 %> 结束标签",
        "auto_fixable": 1,
        "file_path": "test.ejs",
        "line_number": 2,
        "path": None,
    }
    preview = fixer.generate_preview(error, content)
    assert preview is not None
    assert "%>" in preview
    assert "未闭合" in preview


def test_apply_fix_unclosed_tag():
    """Applying fix for unclosed tag should add %> at end."""
    fixer = AutoFixer()
    content = "<%= data.x %>\n<% if (true) { \n"
    error = {
        "category": "EJS",
        "message": "第 2 行：EJS 标签未闭合，缺少 %> 结束标签",
        "auto_fixable": 1,
        "file_path": "test.ejs",
        "line_number": 2,
        "path": None,
    }
    fixed = fixer.apply_fix(error, content)
    assert fixed is not None
    assert fixed.rstrip().endswith("%>")


# ── initvar missing field fix ───────────────────────────────────────

def test_fix_preview_initvar_missing():
    """Preview for missing initvar field should mention the path."""
    fixer = AutoFixer(SIMPLE_SCHEMA)
    content = 'const initvar = {"主角": {"状态": "高兴"}}'
    error = {
        "category": "MVU",
        "message": "initvar 缺少 Schema 必填字段「主角.好感度」",
        "auto_fixable": 1,
        "file_path": "test.yaml",
        "path": "主角.好感度",
    }
    preview = fixer.generate_preview(error, content)
    assert preview is not None
    assert "主角.好感度" in preview


def test_apply_fix_initvar_missing():
    """Applying fix for missing initvar field should add it to the block."""
    fixer = AutoFixer(SIMPLE_SCHEMA)
    content = 'const initvar = {"主角": {"状态": "高兴"}}'
    error = {
        "category": "MVU",
        "message": "initvar 缺少 Schema 必填字段「主角.好感度」",
        "auto_fixable": 1,
        "file_path": "test.yaml",
        "path": "主角.好感度",
    }
    fixed = fixer.apply_fix(error, content)
    assert fixed is not None
    # Parse the fixed content's initvar block
    import re
    match = re.search(r'\{.*\}', fixed, re.DOTALL)
    assert match is not None
    data = json.loads(match.group())
    assert "主角" in data
    assert "好感度" in data["主角"]
    # Default for number should be 0
    assert data["主角"]["好感度"] == 0


def test_apply_fix_initvar_missing_string():
    """Fix for missing string field should add empty string."""
    fixer = AutoFixer(SIMPLE_SCHEMA)
    content = 'const initvar = {"主角": {"好感度": 50}}'
    error = {
        "category": "MVU",
        "message": "initvar 缺少 Schema 必填字段「主角.状态」",
        "auto_fixable": 1,
        "file_path": "test.yaml",
        "path": "主角.状态",
    }
    fixed = fixer.apply_fix(error, content)
    assert fixed is not None
    match = re.search(r'\{.*\}', fixed, re.DOTALL)
    data = json.loads(match.group())
    assert data["主角"]["状态"] == ""


# ── Non-fixable errors ──────────────────────────────────────────────

def test_non_fixable_returns_none():
    """Non-auto-fixable errors should return None for both preview and fix."""
    fixer = AutoFixer()
    error = {"auto_fixable": 0}
    assert fixer.generate_preview(error, "content") is None
    assert fixer.apply_fix(error, "content") is None


def test_unknown_error_type_returns_none():
    """Unknown error types that are auto_fixable should still return None."""
    fixer = AutoFixer()
    error = {
        "category": "MVU",
        "message": "Some unknown error",
        "auto_fixable": 1,
        "file_path": "test.yaml",
        "path": "some.path",
    }
    assert fixer.generate_preview(error, "content") is None
    assert fixer.apply_fix(error, "content") is None
