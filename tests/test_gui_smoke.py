"""GUI smoke tests — run headless with QT_QPA_PLATFORM=offscreen."""
from __future__ import annotations

import json
import os
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
def card_json(tmp_path_factory) -> str:
    tmp = tmp_path_factory.mktemp("gui")
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试角色卡",
        "data": {
            "name": "测试角色卡",
            "first_mes": "你好",
            "extensions": {},
            "character_book": {"name": "世界书", "entries": [
                {"id": "e1", "comment": "条目一",
                 "content": "喜欢：<%= mvu.get(\"主角.好感度\") %>", "enabled": True},
                {"id": "e2", "comment": "未闭合标签",
                 "content": "<p>未闭合：<%= stat_data.主角.好感度", "enabled": True},
                {"id": "e3", "comment": "未转义输出",
                 "content": "<p><%- data.备注 %></p>", "enabled": True},
                {"id": "e4", "comment": "变量初始值",
                 "content": (
                     "# 变量初始值（由 mvu 在开始时读取）\n"
                     "主角:\n"
                     "  好感度: 0\n"
                     "  姓名: 测试\n"
                 ),
                 "enabled": True},
            ]},
        },
    }
    path = tmp / "card.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_main_window_constructs(app, qtbot=None):
    window = MainWindow()
    assert window.windowTitle() == "MVU + EJS 智能检查工具"
    assert window.drop_zone is not None
    assert window.report_panel is not None
    assert window.scan_button.isEnabled() is False
    window.close()


def test_import_card_updates_info(app, card_json):
    window = MainWindow()
    window.import_card(card_json)
    assert "检查块数: 5" in window.info_folder_label.text()  # 4 worldbook + first_mes
    assert "变量初始值" in window.schema_status_label.text()  # data_shape loaded from initvar block
    assert window.scan_button.isEnabled() is True
    window.close()


def test_import_card_without_initvar_shows_degraded(app, tmp_path):
    card = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": "无变量",
        "data": {"name": "无变量", "extensions": {},
                 "character_book": {"name": "wb", "entries": [
                     {"id": "a", "comment": "条目",
                      "content": "<%= stat_data.主角.好感度 %>", "enabled": True}]}},
    }
    path = tmp_path / "noschema.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    window = MainWindow()
    window.import_card(str(path))
    assert "降级" in window.schema_status_label.text()
    window.close()


def test_report_panel_fill_and_filter(app):
    errors = [
        {"level": "Lv.1", "error_id": "EJS-0001", "category": "EJS",
         "file_path": "世界书/条目一", "line_number": 2, "path": None,
         "message": "m1", "suggestion": "s1", "status": "pending"},
        {"level": "Lv.1", "error_id": "EJS-0002", "category": "EJS",
         "file_path": "世界书/条目二", "line_number": None, "path": None,
         "message": "m2", "suggestion": None, "status": "pending"},
        {"level": "Lv.4", "error_id": "EJS-0003", "category": "EJS",
         "file_path": "世界书/条目三", "line_number": 1, "path": "主角.备注",
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


def test_controller_gui_integration(app, card_json):
    """Controller pipeline drives the report panel end to end."""
    controller = AppController()
    controller.import_card(card_json)
    summary = controller.run_static_check()

    panel = ReportPanel()
    panel.show_errors(controller.get_errors(), counts=controller.get_counts())
    assert panel.table.rowCount() == summary.errors_inserted == 3
    controller.close()


def test_report_panel_status_update(app):
    errors = [
        {"level": "Lv.2", "error_id": "EJS-0001", "category": "EJS",
         "file_path": "世界书/条目一", "line_number": 1, "path": None,
         "message": "m", "suggestion": None, "status": "pending"},
    ]
    panel = ReportPanel()
    panel.show_errors(errors, counts={"Lv.1": 0, "Lv.2": 1, "Lv.3": 0, "Lv.4": 0})
    assert panel.table.item(0, 8).text() == "待处理"

    panel.update_status("EJS-0001", "fixed")
    assert panel.table.item(0, 8).text() == "已修复"

    panel.update_status("EJS-0001", "ignored")
    assert panel.table.item(0, 8).text() == "已忽略"


def test_main_window_export_csv(app, card_json, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window = MainWindow()
    window.import_card(card_json)
    window.controller.run_static_check()

    out = tmp_path / "report.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), "CSV 文件 (*.csv)"))
    window._export_report("csv")

    assert out.exists()
    text = out.read_text(encoding="utf-8-sig")
    assert "级别" in text and "EJS-0001" in text
    window.close()


def test_main_window_status_changed_roundtrip(app, card_json):
    window = MainWindow()
    window.import_card(card_json)
    window.controller.run_static_check()
    window.report_panel.show_errors(
        window.controller.get_errors(), counts=window.controller.get_counts()
    )

    first_id = window.controller.get_errors()[0]["error_id"]
    window._on_status_changed(first_id, "fixed")
    assert window.controller.get_errors()[0]["status"] == "fixed"
    assert window.report_panel.table.item(0, 8).text() == "已修复"
    window.close()
