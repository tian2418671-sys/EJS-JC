"""AppController tests — import card → static check → report pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvu_lint.controllers.app_controller import AppController


@pytest.fixture
def card_json(tmp_path: Path) -> str:
    """Build a minimal role-card JSON (chara_card_v2) with broken EJS."""
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试角色卡",
        "data": {
            "name": "测试角色卡",
            "description": "测试卡",
            "first_mes": "你好",
            "extensions": {},
            "character_book": {
                "name": "世界书",
                "entries": [
                    {"id": "e1", "keys": ["好感"], "comment": "条目一",
                     "content": "当前好感：<%= mvu.get(\"主角.好感度\") %>",
                     "enabled": True},
                    {"id": "e2", "keys": ["坏"], "comment": "未闭合标签",
                     "content": "<p>未闭合标签：<%= stat_data.主角.好感度",
                     "enabled": True},
                    {"id": "e3", "keys": ["备注"], "comment": "未转义输出",
                     "content": "<p><%- data.备注 %></p>",
                     "enabled": True},
                    {"id": "e4", "keys": ["初始值"], "comment": "变量初始值",
                     "content": (
                         "# 变量初始值（由 mvu 在开始时读取）\n"
                         "主角:\n"
                         "  好感度: 0\n"
                         "  姓名: 测试\n"
                     ),
                     "enabled": True},
                ],
            },
        },
    }
    path = tmp_path / "card.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_import_card_builds_file_index(card_json):
    controller = AppController()
    project = controller.import_card(card_json)
    assert project is not None
    assert project.card is not None
    by_type = {f.file_path: f.file_type for f in project.files}
    assert "世界书/条目一" in by_type
    assert "世界书/变量初始值" in by_type
    assert "角色卡/开场白" in by_type
    controller.close()


def test_schema_loaded_from_initvar_block(card_json):
    controller = AppController()
    controller.import_card(card_json)
    assert controller.schema_info is not None
    assert controller.schema_info.form == "data_shape"
    assert not controller.degraded_reason()
    paths = controller.schema_info.get_path_set()
    assert "主角.好感度" in paths
    assert "主角.姓名" in paths
    controller.close()


def test_run_static_check_finds_errors(card_json):
    controller = AppController()
    controller.import_card(card_json)
    summary = controller.run_static_check()

    # worldbook x4 + first_mes + description = 6 blocks
    assert summary.total_files == 6
    assert summary.files_scanned == 3   # e1/e2/e3 contain EJS (initvar has none)
    assert summary.errors_inserted == 3  # unclosed tag + <%- unsafe + linkage error for 备注
    assert summary.schema_path_count == 3  # 主角 + 主角.好感度 + 主角.姓名

    errors = controller.get_errors()
    levels = {e["level"] for e in errors}
    assert "Lv.1" in levels  # unclosed tag
    assert "Lv.2" in levels  # linkage error: 备注 not in schema
    assert "Lv.4" in levels  # unsafe output
    controller.close()


def test_error_ids_globally_unique_across_blocks(card_json):
    controller = AppController()
    controller.import_card(card_json)
    controller.run_static_check()
    errors = controller.get_errors()
    ids = [e["error_id"] for e in errors]
    assert len(ids) == len(set(ids))  # no duplicates
    controller.close()


def test_degraded_mode_without_initvar(tmp_path):
    card = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": "无变量",
        "data": {"name": "无变量", "extensions": {},
                 "character_book": {"name": "wb", "entries": [
                     {"id": "a", "comment": "条目",
                      "content": "<%= stat_data.主角.好感度 %>", "enabled": True}]}},
    }
    path = tmp_path / "noschema.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")

    controller = AppController()
    controller.import_card(str(path))
    assert controller.schema_info is None
    assert "变量初始值" in controller.degraded_reason()
    summary = controller.run_static_check()
    assert summary.degraded is True
    assert summary.errors_inserted == 0  # valid ref, no errors
    controller.close()


def test_zip_import_rejected():
    """ZIP import must be rejected — cards are PNG/JSON only."""
    controller = AppController()
    with pytest.raises(ValueError, match="ZIP"):
        controller.import_zip("whatever.zip")
    controller.close()


def test_progress_callback_receives_updates(card_json):
    controller = AppController()
    controller.import_card(card_json)
    updates = []

    def cb(done, total):
        updates.append((done, total))

    controller.run_static_check(progress_cb=cb)
    assert updates
    assert updates[-1][0] == updates[-1][1] == 6
    controller.close()


def test_clear_errors(card_json):
    controller = AppController()
    controller.import_card(card_json)
    controller.run_static_check()
    assert controller.get_errors()
    controller.clear_errors()
    assert controller.get_errors() == []
    controller.close()


def test_run_without_project_raises():
    controller = AppController()
    with pytest.raises(RuntimeError):
        controller.run_static_check()
    controller.close()
