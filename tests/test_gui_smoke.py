"""GUI smoke tests — run headless with QT_QPA_PLATFORM=offscreen."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mvu_lint.controllers.app_controller import AppController  # noqa: E402
from mvu_lint.views.main_window import MainWindow  # noqa: E402
from mvu_lint.views.report_panel import ReportPanel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def card_zip(tmp_path_factory) -> str:
    tmp = tmp_path_factory.mktemp("gui")
    zip_path = tmp / "card.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "schema.json",
            json.dumps({"$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "properties": {"主角": {"type": "object", "properties": {
                            "好感度": {"type": "number"}}}}}),
        )
        zf.writestr(
            "世界书/entry.json",
            json.dumps({"content": "喜欢：<%= mvu.get(\"主角.好感度\") %>"}),
        )
        zf.writestr("世界书/broken.html", "<p>未闭合：<%= stat_data.主角.好感度")
        zf.writestr("世界书/unsafe.html", "<p><%- data.备注 %></p>")
    return str(zip_path)


def test_main_window_constructs(app, qtbot=None):
    window = MainWindow()
    assert window.windowTitle() == "MVU + EJS 智能检查工具"
    assert window.drop_zone is not None
    assert window.report_panel is not None
    assert window.scan_button.isEnabled() is False
    window.close()


def test_import_zip_updates_info(app, card_zip):
    window = MainWindow()
    window.import_zip(card_zip)
    assert "文件数: 4" in window.info_folder_label.text()
    assert "schema.json 解析成功" in window.schema_status_label.text()
    assert window.scan_button.isEnabled() is True
    window.close()


def test_import_zip_without_schema_shows_degraded(app, tmp_path):
    zip_path = tmp_path / "noschema.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("世界书/a.html", "<%= stat_data.主角.好感度 %>")
    window = MainWindow()
    window.import_zip(str(zip_path))
    assert "降级" in window.schema_status_label.text()
    window.close()


def test_report_panel_fill_and_filter(app):
    errors = [
        {"level": "Lv.1", "error_id": "EJS-0001", "category": "EJS",
         "file_path": "a.html", "line_number": 2, "path": None,
         "message": "m1", "suggestion": "s1", "status": "pending"},
        {"level": "Lv.1", "error_id": "EJS-0002", "category": "EJS",
         "file_path": "b.html", "line_number": None, "path": None,
         "message": "m2", "suggestion": None, "status": "pending"},
        {"level": "Lv.4", "error_id": "EJS-0003", "category": "EJS",
         "file_path": "c.html", "line_number": 1, "path": "主角.备注",
         "message": "m3", "suggestion": "s3", "status": "pending"},
    ]
    panel = ReportPanel()
    panel.show_errors(errors, counts={"Lv.1": 2, "Lv.2": 0, "Lv.3": 0, "Lv.4": 1})
    assert panel.table.rowCount() == 3

    panel.filter_combo.setCurrentText("Lv.1")
    assert panel.table.rowCount() == 2

    panel.filter_combo.setCurrentText("Lv.4")
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 5).text() == "主角.备注"

    panel.filter_combo.setCurrentText("全部")
    assert panel.table.rowCount() == 3
    panel.clear()
    assert panel.table.rowCount() == 0


def test_controller_gui_integration(app, card_zip):
    """Controller pipeline drives the report panel end to end."""
    controller = AppController()
    controller.import_zip(card_zip)
    summary = controller.run_static_check()

    panel = ReportPanel()
    panel.show_errors(controller.get_errors(), counts=controller.get_counts())
    assert panel.table.rowCount() == summary.errors_inserted == 3
    controller.close()


def test_report_panel_status_update(app):
    errors = [
        {"level": "Lv.2", "error_id": "EJS-0001", "category": "EJS",
         "file_path": "a.html", "line_number": 1, "path": None,
         "message": "m", "suggestion": None, "status": "pending"},
    ]
    panel = ReportPanel()
    panel.show_errors(errors, counts={"Lv.1": 0, "Lv.2": 1, "Lv.3": 0, "Lv.4": 0})
    assert panel.table.item(0, 8).text() == "待处理"

    panel.update_status("EJS-0001", "fixed")
    assert panel.table.item(0, 8).text() == "已修复"

    panel.update_status("EJS-0001", "ignored")
    assert panel.table.item(0, 8).text() == "已忽略"


def test_main_window_export_csv(app, card_zip, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window = MainWindow()
    window.import_zip(card_zip)
    window.controller.run_static_check()

    out = tmp_path / "report.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), "CSV 文件 (*.csv)"))
    window._export_report("csv")

    assert out.exists()
    text = out.read_text(encoding="utf-8-sig")
    assert "级别" in text and "EJS-0001" in text
    window.close()


def test_main_window_status_changed_roundtrip(app, card_zip):
    window = MainWindow()
    window.import_zip(card_zip)
    window.controller.run_static_check()
    window.report_panel.show_errors(
        window.controller.get_errors(), counts=window.controller.get_counts()
    )

    first_id = window.controller.get_errors()[0]["error_id"]
    window._on_status_changed(first_id, "fixed")
    assert window.controller.get_errors()[0]["status"] == "fixed"
    assert window.report_panel.table.item(0, 8).text() == "已修复"
    window.close()