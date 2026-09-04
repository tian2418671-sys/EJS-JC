"""Unit tests for <UpdateVariable> + JSON Patch path validation."""
from __future__ import annotations

from mvu_lint.core.schema_loader import SchemaLoader
from mvu_lint.core.static_checker import StaticChecker
from mvu_lint.models.check_result import ErrorLevel


def _make_schema_info():
    loader = SchemaLoader()
    return loader.load_from_dict({
        "世界": {"当前时间": "2026年9月", "天气": "晴"},
        "主角": {"体力": 100, "状态": "正常"},
        "物品": {"长剑": {"描述": "剑", "状态": "持有"}},
        "任务": [{"名称": "任务A", "进度": 0}],
        "金钱": {"现金": 100},
    })


SCHEMA = _make_schema_info()


def _wrap(json_body: str) -> str:
    return (
        "<UpdateVariable>\n"
        "<analysis>预览</analysis>\n"
        "<JSONPatch>\n"
        f"{json_body}\n"
        "</JSONPatch>\n"
        "</UpdateVariable>"
    )


# ── valid concrete patches ──────────────────────────────────────────

def test_valid_replace_add_remove_move():
    checker = StaticChecker()
    content = _wrap(
        '[{"op":"replace","path":"/世界/当前时间","value":"2026年10月"},'
        '{"op":"add","path":"/物品/新剑","value":{"描述":"剑","状态":"持有"}},'
        '{"op":"remove","path":"/任务/0"},'
        '{"op":"move","from":"/金钱/现金","path":"/金钱/备用"}]'
    )
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_valid_array_index_maps_to_wildcard():
    checker = StaticChecker()
    content = _wrap('[{"op":"replace","path":"/任务/0/进度","value":50}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


# ── structural / format checks ──────────────────────────────────────

def test_unparseable_json_is_skipped():
    """A <JSONPatch> body that is not JSON is a template/prose mention,
    not concrete data — it must be skipped silently."""
    checker = StaticChecker()
    content = _wrap("not a json array")
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_prose_mention_of_tags_is_skipped():
    """Instruction prose that merely mentions <UpdateVariable> must not
    produce findings (real cards are full of such prose)."""
    checker = StaticChecker()
    content = (
        "- 正文之后只输出一个位于回复末尾的 <UpdateVariable> 变量块；"
        "变量块内必须先输出 <analysis>，再输出 <JSONPatch> 数组"
    )
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_prose_jsonpatch_array_word_is_skipped():
    """The prose '<JSONPatch>数组</JSONPatch>' (meaning 'a JSONPatch array')
    is not a concrete patch and must be skipped."""
    checker = StaticChecker()
    content = (
        "输出顺序为 正文 → <UpdateVariable><analysis>变量预分析</analysis>"
        "<JSONPatch>数组</JSONPatch></UpdateVariable>"
    )
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_unclosed_update_variable_is_skipped():
    checker = StaticChecker()
    content = "<UpdateVariable><JSONPatch>[{\"op\":\"replace\",\"path\":\"/世界/天气\",\"value\":\"雨\"}]</JSONPatch>"
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_missing_op_field():
    checker = StaticChecker()
    content = _wrap('[{"path":"/世界/天气","value":"雨"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2
    assert "op" in results[0].message


def test_unsupported_op():
    checker = StaticChecker()
    content = _wrap('[{"op":"test","path":"/世界/天气","value":"雨"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3


def test_move_missing_from():
    checker = StaticChecker()
    content = _wrap('[{"op":"move","path":"/金钱/备用"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2
    assert "from" in results[0].message


def test_invalid_json_pointer():
    checker = StaticChecker()
    content = _wrap('[{"op":"replace","path":"世界/天气","value":"雨"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV2


def test_unclosed_update_variable_is_skipped():
    """An unclosed <UpdateVariable> in prose is not concrete data and
    must be skipped."""
    checker = StaticChecker()
    content = "<UpdateVariable><JSONPatch>[{\"op\":\"replace\",\"path\":\"/世界/天气\",\"value\":\"雨\"}]</JSONPatch>"
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


# ── schema linkage checks ───────────────────────────────────────────

def test_replace_path_not_in_schema():
    checker = StaticChecker()
    content = _wrap('[{"op":"replace","path":"/世界/不存在","value":1}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "不存在" in results[0].message


def test_replace_type_mismatch():
    checker = StaticChecker()
    content = _wrap('[{"op":"replace","path":"/主角/体力","value":"一百"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "类型不匹配" in results[0].message


def test_remove_path_not_in_schema():
    checker = StaticChecker()
    content = _wrap('[{"op":"remove","path":"/金钱/不存在"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3


def test_add_new_key_under_existing_container():
    checker = StaticChecker()
    content = _wrap('[{"op":"add","path":"/物品/匕首","value":{"描述":"短刀"}}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_add_missing_parent():
    checker = StaticChecker()
    content = _wrap('[{"op":"add","path":"/不存在容器/新键","value":1}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "父路径" in results[0].message


def test_add_new_top_level_not_in_schema():
    checker = StaticChecker()
    content = _wrap('[{"op":"add","path":"/未知顶层","value":{}}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert len(results) == 1
    assert results[0].level == ErrorLevel.LV3
    assert "顶层变量" in results[0].message


def test_move_from_not_in_schema():
    checker = StaticChecker()
    content = _wrap('[{"op":"move","from":"/金钱/不存在","path":"/金钱/备用"}]')
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert any(r.level == ErrorLevel.LV3 for r in results)


# ── template / degraded handling ────────────────────────────────────

def test_template_spec_is_skipped():
    checker = StaticChecker()
    content = (
        "<UpdateVariable>\n"
        "<JSONPatch>\n"
        '[{"op":"replace","path":"/<顶层根>/<既有字段路径>","value":"<正文确定的新值>"}]\n'
        "</JSONPatch>\n"
        "</UpdateVariable>"
    )
    results = checker.check_json_patch(content, "test", SCHEMA)
    assert results == []


def test_no_schema_skips_linkage():
    checker = StaticChecker()
    content = _wrap('[{"op":"replace","path":"/任意/路径","value":1}]')
    results = checker.check_json_patch(content, "test", schema_info=None)
    # format is valid; linkage is skipped in degraded mode
    assert results == []
