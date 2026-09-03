"""Unit tests for EJSParser."""
import pytest
from mvu_lint.core.ejs_parser import EJSParser


def test_unclosed_tag_detected():
    """Unclosed <% tags should be detected as Lv.1 errors."""
    parser = EJSParser()
    content = "<%= data.x %>\n<% if (true) { \n"
    result = parser.parse(content, "test.ejs")
    lv1_errors = [e for e in result.check_results if e.level.value == "Lv.1"]
    assert len(lv1_errors) >= 1
    assert any("未闭合" in e.message for e in lv1_errors)


def test_static_variable_extraction():
    """Static variable paths should be correctly extracted."""
    parser = EJSParser()
    content = "<%= stat_data.主角.好感度 %>"
    result = parser.parse(content, "test.ejs")
    assert len(result.variable_refs) == 1
    ref = result.variable_refs[0]
    assert ref.is_static is True
    assert ref.path == "主角.好感度"
    assert ref.is_safe is True


def test_dangerous_output_flagged():
    """<%- tags should be flagged as Lv.4 security warnings."""
    parser = EJSParser()
    content = "<%- data.物品栏[0].名称 %>"
    result = parser.parse(content, "test.ejs")
    lv4 = [e for e in result.check_results if e.level.value == "Lv.4"]
    assert len(lv4) == 1
    assert "未转义" in lv4[0].message
    # Variable ref should still be extracted
    ref = result.variable_refs[0]
    assert ref.is_safe is False
    assert ref.is_static is True
    assert ref.path == "物品栏.0.名称"


def test_dynamic_property_not_static():
    """Dynamic property names should be flagged as non-static, not errored."""
    parser = EJSParser()
    content = "<%= vars[props.key] %>"
    result = parser.parse(content, "test.ejs")
    assert len(result.variable_refs) == 1
    ref = result.variable_refs[0]
    assert ref.is_static is False
    assert ref.path is None
    assert "动态" in (ref.note or "")


def test_mvu_get_pattern():
    """mvu.get('X.Y') pattern should be extracted correctly."""
    parser = EJSParser()
    content = "<%= mvu.get('主角.能力面板.力量') %>"
    result = parser.parse(content, "test.ejs")
    ref = result.variable_refs[0]
    assert ref.is_static is True
    assert ref.path == "主角.能力面板.力量"


def test_stray_close_tag_detected():
    """Stray %> without opening <% should be detected as Lv.1."""
    parser = EJSParser()
    content = "普通文本 %> 更多文本"
    result = parser.parse(content, "test.ejs")
    lv1 = [e for e in result.check_results if e.level.value == "Lv.1"]
    assert len(lv1) >= 1
    assert any("孤立" in e.message for e in lv1)


def test_clean_ejs_no_errors():
    """Well-formed EJS should produce no errors."""
    parser = EJSParser()
    content = "<%= stat_data.x %> <%= mvu.get('y') %>"
    result = parser.parse(content, "test.ejs")
    assert len(result.check_results) == 0
    assert len(result.variable_refs) == 2
