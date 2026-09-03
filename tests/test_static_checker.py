"""Unit tests for StaticChecker — MVU commands, linkage, initvar checks."""
from __future__ import annotations

from mvu_lint.core.ejs_parser import EJSParser, EJSVariableReference
from mvu_lint.core.schema_loader import SchemaLoader
from mvu_lint.core.static_checker import StaticChecker
from mvu_lint.models.check_result import ErrorLevel


# ── Fixtures ────────────────────────────────────────────────────────

def _make_schema_info():
    """Build a SchemaInfo from a pure data-shape dict."""
    loader = SchemaLoader()
    return loader.load_from_dict({
        "主角": {
            "好感度": 50,        # number
            "状态": "高兴",       # string
            "物品栏": [
                {"名称": "剑", "数量": 1}
            ]
        }
    })


SIMPLE_SCHEMA = _make_schema_info()


# ── MVU command format checks ───────────────────────────────────────

def test_mvu_valid_command_no_errors():
    """Well-formed MVU commands with valid paths should produce no errors."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.好感度 += 5 -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_mvu_missing_operator():
    """MVU command without operator should be Lv.2."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.好感度 50 -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2
    assert "格式错误" in results[0].message


def test_mvu_missing_value():
    """MVU command without value should be Lv.2."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.好感度 = -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2


def test_mvu_path_not_in_schema():
    """MVU command with path not in schema should be Lv.3."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.不存在的字段 = 10 -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "不存在" in results[0].message


def test_mvu_type_mismatch():
    """MVU command with wrong type value should be Lv.3."""
    checker = StaticChecker()
    # 好感度 is number, but we assign a string
    content = '<!-- mvu: 主角.好感度 = "hello" -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "类型不匹配" in results[0].message


def test_mvu_assign_to_object():
    """Assigning to an object/array path should be Lv.3."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.物品栏 = "剑" -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "object" in results[0].message or "array" in results[0].message


def test_mvu_plus_minus_on_string():
    """+= or -= on a string field should be Lv.3."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.状态 += "高兴" -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3


def test_mvu_array_index_path():
    """MVU command with numeric index should match * wildcard path."""
    checker = StaticChecker()
    # 物品栏.*.数量 is a valid path, so 物品栏[0].数量 should match
    content = '<!-- mvu: 主角.物品栏.0.数量 = 5 -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_mvu_no_schema_skips_path_check():
    """Without schema, only format errors are reported (degraded mode)."""
    checker = StaticChecker()
    content = '<!-- mvu: any.path.here = 10 -->'
    results = checker.check_mvu_commands(content, "test.yaml", schema_info=None)
    assert len(results) == 0  # format is valid, path not checked


def test_mvu_string_value_with_quotes():
    """String value with quotes should parse correctly."""
    checker = StaticChecker()
    content = '<!-- mvu: 主角.状态 = "兴奋" -->'
    results = checker.check_mvu_commands(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 0


# ── Linkage checks ──────────────────────────────────────────────────

def test_linkage_valid_path():
    """EJS variable with valid schema path should produce no errors."""
    checker = StaticChecker()
    refs = [EJSVariableReference(
        raw="<%= stat_data.主角.好感度 %>",
        path="主角.好感度",
        line=1,
        is_safe=True,
        is_static=True,
    )]
    results = checker.check_linkage(refs, "test.ejs", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_linkage_invalid_path():
    """EJS variable with non-existent schema path should be Lv.2."""
    checker = StaticChecker()
    refs = [EJSVariableReference(
        raw="<%= stat_data.主角.不存在 %>",
        path="主角.不存在",
        line=1,
        is_safe=True,
        is_static=True,
    )]
    results = checker.check_linkage(refs, "test.ejs", SIMPLE_SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2
    assert "不存在" in results[0].message


def test_linkage_skips_non_static():
    """Non-static refs should be skipped in linkage check."""
    checker = StaticChecker()
    refs = [EJSVariableReference(
        raw="<%= vars[props.key] %>",
        path=None,
        line=1,
        is_safe=True,
        is_static=False,
    )]
    results = checker.check_linkage(refs, "test.ejs", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_linkage_no_schema():
    """Linkage check should return empty when schema is None."""
    checker = StaticChecker()
    refs = [EJSVariableReference(
        raw="<%= stat_data.anything %>",
        path="anything",
        line=1,
        is_safe=True,
        is_static=True,
    )]
    results = checker.check_linkage(refs, "test.ejs", schema_info=None)
    assert len(results) == 0


def test_linkage_array_index():
    """EJS ref with numeric index should match wildcard path."""
    checker = StaticChecker()
    refs = [EJSVariableReference(
        raw="<%= stat_data.主角.物品栏.0.名称 %>",
        path="主角.物品栏.0.名称",
        line=1,
        is_safe=True,
        is_static=True,
    )]
    results = checker.check_linkage(refs, "test.ejs", SIMPLE_SCHEMA)
    assert len(results) == 0


# ── initvar checks ──────────────────────────────────────────────────

def test_initvar_complete_no_errors():
    """initvar with all schema leaf fields should produce no errors."""
    checker = StaticChecker()
    content = '''const initvar = {
    "主角": {
        "好感度": 50,
        "状态": "高兴",
        "物品栏": [
            {"名称": "剑", "数量": 1}
        ]
    }
}'''
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_initvar_missing_field():
    """initvar missing a schema leaf field should be Lv.2."""
    checker = StaticChecker()
    content = '''const initvar = {
    "主角": {
        "状态": "高兴"
    }
}'''
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    missing = [r for r in results if "缺少" in r.message]
    assert len(missing) >= 1
    assert all(r.level == ErrorLevel.LV2 for r in missing)
    assert all(r.auto_fixable for r in missing)


def test_initvar_type_mismatch():
    """initvar with wrong type should be Lv.2."""
    checker = StaticChecker()
    content = '''const initvar = {
    "主角": {
        "好感度": "应该是个数字",
        "状态": "高兴",
        "物品栏": [
            {"名称": "剑", "数量": 1}
        ]
    }
}'''
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    type_errors = [r for r in results if "类型不匹配" in r.message]
    assert len(type_errors) >= 1
    assert all(r.level == ErrorLevel.LV2 for r in type_errors)


def test_initvar_extra_field():
    """initvar with extra field not in schema should be Lv.3."""
    checker = StaticChecker()
    content = '''const initvar = {
    "主角": {
        "好感度": 50,
        "状态": "高兴",
        "物品栏": [
            {"名称": "剑", "数量": 1}
        ],
        "多余字段": "hello"
    }
}'''
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    extra = [r for r in results if "未定义" in r.message]
    assert len(extra) >= 1
    assert all(r.level == ErrorLevel.LV3 for r in extra)


def test_initvar_no_schema():
    """initvar check should return empty when schema is None."""
    checker = StaticChecker()
    content = 'const initvar = { "x": 1 }'
    results = checker.check_initvar(content, "test.yaml", schema_info=None)
    assert len(results) == 0


def test_initvar_no_initvar_block():
    """Content without initvar block should return empty."""
    checker = StaticChecker()
    content = 'some other content without initvar'
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    assert len(results) == 0


def test_initvar_js_unquoted_keys():
    """initvar with JS-style unquoted keys should still parse."""
    checker = StaticChecker()
    content = '''const initvar = {
    主角: {
        好感度: 50,
        状态: "高兴",
        物品栏: [
            {名称: "剑", 数量: 1}
        ]
    }
}'''
    results = checker.check_initvar(content, "test.yaml", SIMPLE_SCHEMA)
    # Should parse and find no missing fields
    missing = [r for r in results if "缺少" in r.message]
    assert len(missing) == 0
