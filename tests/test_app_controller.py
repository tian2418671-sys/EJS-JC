"""AppController tests — import ZIP → static check → report pipeline."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mvu_lint.controllers.app_controller import AppController


@pytest.fixture
def card_zip(tmp_path: Path) -> str:
    """Build a minimal role-card ZIP with broken EJS."""
    zip_path = tmp_path / "card.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "schema.json",
            json.dumps({"$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "properties": {"主角": {"type": "object",
                                                "properties": {"好感度": {"type": "number"}}}}}),
        )
        zf.writestr(
            "世界书/entry.json",
            json.dumps({"content": "当前好感：<%= mvu.get(\"主角.好感度\") %>"}),
        )
        zf.writestr(
            "世界书/broken.html",
            "<p>未闭合标签：<%= stat_data.主角.好感度",
        )
        zf.writestr(
            "脚本/helper.js",
            "// 无 EJS 内容 \nconsole.log('hi');",
        )
        zf.writestr(
            "世界书/unsafe.html",
            "<p><%- data.备注 %></p>",
        )
    return str(zip_path)


def test_import_zip_builds_file_index(card_zip):
    controller = AppController()
    project = controller.import_zip(card_zip)
    assert project is not None
    assert project.schema_form == "json"
    assert project.schema_path is not None
    by_type = {f.file_path: f.file_type for f in project.files}
    # schema.json is indexed, but flagged as schema (skipped by checks)
    assert by_type.get("schema.json") == "schema"
    assert "世界书/entry.json" in by_type
    assert "脚本/helper.js" in by_type
    controller.close()


def test_schema_loaded(card_zip):
    controller = AppController()
    controller.import_zip(card_zip)
    assert controller.schema_info is not None
    assert controller.schema_info.form == "json_schema"
    assert not controller.degraded_reason()
    controller.close()


def test_run_static_check_finds_errors(card_zip):
    controller = AppController()
    controller.import_zip(card_zip)
    summary = controller.run_static_check()

    assert summary.total_files == 5     # 世界书 x3 + 脚本 x1 + schema.json
    assert summary.files_scanned == 3   # helper.js contains no EJS
    assert summary.errors_inserted == 3  # unclosed tag + <%- unsafe + linkage error for 备注
    assert summary.schema_path_count == 2  # 主角 (object) + 主角.好感度 (leaf)

    errors = controller.get_errors()
    levels = {e["level"] for e in errors}
    assert "Lv.1" in levels  # unclosed tag
    assert "Lv.2" in levels  # linkage error: 备注 not in schema
    assert "Lv.4" in levels  # unsafe output
    controller.close()


def test_error_ids_globally_unique_across_files(card_zip):
    controller = AppController()
    controller.import_zip(card_zip)
    controller.run_static_check()
    errors = controller.get_errors()
    ids = [e["error_id"] for e in errors]
    assert len(ids) == len(set(ids))  # no duplicates
    controller.close()


def test_degraded_mode_without_schema(tmp_path):
    zip_path = tmp_path / "noschema.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "世界书/a.html",
            "<%= stat_data.主角.好感度 %>",
        )
    controller = AppController()
    controller.import_zip(str(zip_path))
    assert controller.schema_info is None
    assert "schema.json" in controller.degraded_reason()
    summary = controller.run_static_check()
    assert summary.degraded is True
    assert summary.errors_inserted == 0  # valid ref, no errors
    controller.close()


def test_progress_callback_receives_updates(card_zip):
    controller = AppController()
    controller.import_zip(card_zip)
    updates = []

    def cb(done, total):
        updates.append((done, total))

    controller.run_static_check(progress_cb=cb)
    assert updates
    assert updates[-1][0] == updates[-1][1] == 5
    controller.close()


def test_clear_errors(card_zip):
    controller = AppController()
    controller.import_zip(card_zip)
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