"""Unit tests for card_loader initvar extraction + extension robustness."""
import json
import pytest
from mvu_lint.core.card_loader import (
    load_card,
    extract_schema_dict,
    CharacterCard,
)


def _card_dict(entries, extensions=None):
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试卡",
        "data": {
            "name": "测试卡",
            "character_book": {"name": "书", "entries": entries},
            "extensions": extensions or {},
        },
    }


def _write_card(tmp_path, card_dict, name="card.json"):
    path = tmp_path / name
    path.write_text(json.dumps(card_dict, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_tavern_helper_as_list_does_not_crash(tmp_path):
    """extensions.tavern_helper may be a list of [key, value] pairs."""
    card = _card_dict(
        [{"id": "e1", "comment": "条目一", "content": "<%= data.x %>"}],
        extensions={
            "tavern_helper": [
                ["scripts", [
                    {"type": "script", "enabled": True,
                     "name": "mvu", "id": "x",
                     "content": "import '.../bundle.js';"},
                ]],
                ["variables", {}],
            ]
        },
    )
    loaded = load_card(_write_card(tmp_path, card))
    assert any(b.file_path == "脚本/tavern_helper_000" for b in loaded.blocks)
    assert any("bundle.js" in b.content for b in loaded.blocks)


def test_initvar_detected_by_label(tmp_path):
    """[InitVar] worldbook entry label should trigger schema extraction."""
    card = _card_dict([
        {
            "id": "iv", "comment": "[InitVar]请勿打开",
            "content": "---\n世界:\n  当前幕: 第一幕\n主角:\n  好感度: 0\n",
        },
    ])
    loaded = load_card(_write_card(tmp_path, card))
    schema = extract_schema_dict(loaded)
    assert schema == {"世界": {"当前幕": "第一幕"}, "主角": {"好感度": 0}}


def test_initvar_json_meta_stripped(tmp_path):
    """JSON initvar with $meta/$schema keys should strip metadata."""
    card = _card_dict([
        {
            "id": "iv", "comment": "[InitVar]",
            "content": json.dumps({
                "$meta": {"extensible": True, "version": "7.1"},
                "MC": {
                    "$meta": {"extensible": True},
                    "系统": {"当前地点": "", "当前时间": {"日期": ""}},
                },
            }, ensure_ascii=False),
        },
    ])
    loaded = load_card(_write_card(tmp_path, card))
    schema = extract_schema_dict(loaded)
    assert "$meta" not in schema
    assert schema["MC"]["系统"]["当前地点"] == ""
    assert schema["MC"]["系统"]["当前时间"]["日期"] == ""


def test_initvar_empty_placeholder_skipped(tmp_path):
    """A blank [InitVar] placeholder before the real block is skipped."""
    card = _card_dict([
        {"id": "iv1", "comment": "InitVar不要开", "content": ""},
        {
            "id": "iv2", "comment": "[InitVar]",
            "content": "主角:\n  好感度: 5\n",
        },
    ])
    loaded = load_card(_write_card(tmp_path, card))
    schema = extract_schema_dict(loaded)
    assert schema == {"主角": {"好感度": 5}}


def test_character_book_as_list_does_not_crash(tmp_path):
    """character_book may be absent/malformed without crashing block build."""
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试卡",
        "data": {
            "name": "测试卡",
            "character_book": [],
            "extensions": {"regex_scripts": "not-a-list"},
        },
    }
    loaded = load_card(_write_card(tmp_path, card))
    assert loaded.blocks is not None
