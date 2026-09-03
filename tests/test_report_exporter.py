"""Tests for mvu_lint.utils.report_exporter."""
from __future__ import annotations

import csv
from datetime import datetime

from mvu_lint.utils.report_exporter import (
    export_csv,
    export_html,
    export_markdown,
    _sorted,
)


_SAMPLE = [
    {"level": "Lv.2", "error_id": "EJS-0010", "category": "EJS",
     "file_path": "世界书/a.html", "line_number": 3, "path": "主角.好感度",
     "message": "未闭合标签", "suggestion": "补全 %>", "status": "pending"},
    {"level": "Lv.1", "error_id": "EJS-0007", "category": "EJS",
     "file_path": "世界书/b.html", "line_number": 1, "path": None,
     "message": "致命错误", "suggestion": None, "status": "pending"},
    {"level": "Lv.4", "error_id": "EJS-0002", "category": "EJS",
     "file_path": "世界书/c.html", "line_number": None, "path": "数据.备注",
     "message": "未转义输出", "suggestion": "改用 <%= %>", "status": "ignored"},
]


def test_sorted_by_severity_then_id():
    ordered = _sorted(_SAMPLE)
    ids = [e["error_id"] for e in ordered]
    # Lv.1 first, then Lv.2, then Lv.4
    assert ids == ["EJS-0007", "EJS-0010", "EJS-0002"]


def test_sorted_numeric_aware():
    data = [
        {"level": "Lv.2", "error_id": "EJS-0010"},
        {"level": "Lv.2", "error_id": "EJS-0002"},
        {"level": "Lv.2", "error_id": "EJS-0015"},
    ]
    assert [e["error_id"] for e in _sorted(data)] == [
        "EJS-0002", "EJS-0010", "EJS-0015",
    ]


def test_export_csv(tmp_path):
    out = tmp_path / "report.csv"
    n = export_csv(_SAMPLE, str(out))
    assert n == 3
    text = out.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    assert lines[0].startswith("级别,ID,类别")
    assert len(lines) == 4  # header + 3 rows


def test_export_markdown(tmp_path):
    out = tmp_path / "report.md"
    n = export_markdown(_SAMPLE, str(out))
    assert n == 3
    text = out.read_text(encoding="utf-8")
    assert text.startswith("| 级别 | ID |")
    assert "EJS-0007" in text


def test_export_html(tmp_path):
    out = tmp_path / "report.html"
    n = export_html(
        _SAMPLE, str(out), project_name="测试卡.zip", schema_form="json",
        degraded=False, counts={"Lv.1": 1, "Lv.2": 1, "Lv.3": 0, "Lv.4": 1},
        generated_at=datetime(2026, 9, 4, 0, 30, 0),
    )
    assert n == 3
    text = out.read_text(encoding="utf-8")
    assert "MVU + EJS 智能检查报告" in text
    assert "测试卡.zip" in text
    assert "Lv.1: 1" in text
    assert "EJS-0007" in text
    # Chinese should be intact (not mojibake)
    assert "未闭合标签" in text


def test_export_html_escapes_special_chars(tmp_path):
    out = tmp_path / "report.html"
    export_html(
        [{"level": "Lv.1", "error_id": "EJS-0001", "category": "EJS",
          "file_path": "a<b>.html", "line_number": 1, "path": None,
          "message": "<script>alert(1)</script>", "suggestion": None,
          "status": "pending"}],
        str(out),
    )
    text = out.read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "a&lt;b&gt;.html" in text
