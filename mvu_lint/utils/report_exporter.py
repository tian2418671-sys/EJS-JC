"""Report exporter — serialize static-check results to CSV / HTML / Markdown.

Kept Qt-free so it is fully unit-testable and reusable by both the GUI
(File → 导出报告) and any future CLI batch mode.
"""
from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_FIELDS = [
    ("level", "级别"),
    ("error_id", "ID"),
    ("category", "类别"),
    ("file_path", "文件"),
    ("line_number", "行"),
    ("path", "变量路径"),
    ("message", "消息"),
    ("suggestion", "建议"),
    ("status", "状态"),
]

_LEVEL_ORDER = ["Lv.1", "Lv.2", "Lv.3", "Lv.4"]


def _sorted(errors: List[dict]) -> List[dict]:
    """Stable sort: by severity then error_id (numeric-aware)."""
    def key(err: dict) -> tuple:
        lvl = _LEVEL_ORDER.index(err.get("level")) if err.get("level") in _LEVEL_ORDER else 99
        rid = err.get("error_id") or ""
        # numeric-aware id sort: "EJS-0007" < "EJS-0010"
        digits = "".join(ch for ch in rid if ch.isdigit())
        return (lvl, int(digits) if digits else 0)
    return sorted(errors, key=key)


def _cell(err: dict, field: str) -> str:
    value = err.get(field)
    if value is None:
        return ""
    return str(value)


def export_csv(errors: List[dict], path: str) -> int:
    """Write errors to a CSV file (UTF-8 with BOM for Excel). Returns row count."""
    rows = _sorted(errors)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in _FIELDS])
        for err in rows:
            writer.writerow([_cell(err, field) for field, _ in _FIELDS])
    return len(rows)


def export_markdown(errors: List[dict], path: str) -> int:
    """Write a GitHub-flavoured Markdown table. Returns row count."""
    rows = _sorted(errors)
    header = "| " + " | ".join(label for _, label in _FIELDS) + " |"
    sep = "| " + " | ".join("---" for _ in _FIELDS) + " |"
    lines = [header, sep]
    for err in rows:
        cells = [_cell(err, field).replace("|", "\\|").replace("\n", " ") for field, _ in _FIELDS]
        lines.append("| " + " | ".join(cells) + " |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


_LEVEL_BADGE = {
    "Lv.1": ("#e5534b", "Lv.1 致命"),
    "Lv.2": ("#e8934a", "Lv.2 严重"),
    "Lv.3": ("#e8b64c", "Lv.3 警告"),
    "Lv.4": ("#6cb2e8", "Lv.4 安全"),
}


def export_html(errors: List[dict], path: str,
                project_name: str = "",
                schema_form: str = "",
                degraded: bool = False,
                counts: Optional[dict] = None,
                generated_at: Optional[datetime] = None) -> int:
    """Write a self-contained dark-theme HTML report. Returns row count."""
    rows = _sorted(errors)
    generated_at = generated_at or datetime.now()

    counts = counts or {}
    summary_parts = []
    for lv in _LEVEL_ORDER:
        n = counts.get(lv, 0)
        color = _LEVEL_BADGE[lv][0]
        summary_parts.append(f'<span class="chip" style="--c:{color}">{lv}: {n}</span>')
    total = sum(counts.values()) if counts else len(rows)
    summary_html = " ".join(summary_parts) if summary_parts else ""

    status_line = []
    if project_name:
        status_line.append(f"项目: <b>{html.escape(project_name)}</b>")
    if schema_form:
        status_line.append(f"Schema: <b>{html.escape(schema_form)}</b>")
    if degraded:
        status_line.append('<span class="warn">⚠️ 降级模式</span>')

    body_rows = []
    for err in rows:
        lv = err.get("level", "")
        badge = _LEVEL_BADGE.get(lv, ("#8b93a3", lv or "?"))
        line = _cell(err, "line_number") or "—"
        path_val = _cell(err, "path")
        body_rows.append(
            "<tr>"
            f'<td><span class="badge" style="--c:{badge[0]}">{html.escape(badge[1])}</span></td>'
            f"<td>{html.escape(_cell(err, 'error_id'))}</td>"
            f"<td>{html.escape(_cell(err, 'category'))}</td>"
            f"<td class=\"mono\">{html.escape(_cell(err, 'file_path'))}</td>"
            f"<td class=\"num\">{html.escape(line)}</td>"
            f"<td class=\"mono\">{html.escape(path_val)}</td>"
            f"<td>{html.escape(_cell(err, 'message'))}</td>"
            f"<td>{html.escape(_cell(err, 'suggestion'))}</td>"
            f"<td>{html.escape(_cell(err, 'status'))}</td>"
            "</tr>"
        )

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>检查报告 — {html.escape(project_name or 'MVU + EJS')}</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 32px;
  font-family: "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif;
  background: #1e2128; color: #d8dce4; font-size: 14px;
}}
h1 {{ font-size: 22px; margin: 0 0 4px; color: #ffffff; }}
.meta {{ color: #8b93a3; margin-bottom: 20px; }}
.meta b {{ color: #cfe3ff; }}
.warn {{ color: #e8b64c; }}
.summary {{ margin-bottom: 20px; }}
.chip {{
  display: inline-block; padding: 3px 12px; border-radius: 12px;
  margin-right: 10px; font-weight: bold;
  color: var(--c); border: 1px solid var(--c); background: transparent;
}}
table {{ width: 100%; border-collapse: collapse; background: #22262e; }}
th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #2e333d; vertical-align: top; }}
th {{ background: #2b303a; color: #a8b0c0; font-weight: bold; position: sticky; top: 0; }}
tr:nth-child(even) td {{ background: #262b34; }}
.badge {{ color: var(--c); font-weight: bold; white-space: nowrap; }}
.mono {{ font-family: Consolas, "Courier New", monospace; font-size: 13px; }}
.num {{ text-align: center; white-space: nowrap; }}
footer {{ margin-top: 24px; color: #6a7180; font-size: 12px; }}
</style>
</head>
<body>
<h1>MVU + EJS 智能检查报告</h1>
<div class="meta">{'　'.join(status_line)}　生成时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}</div>
<div class="summary">共 <b>{total}</b> 条　{summary_html}</div>
<table>
<thead><tr>
  <th>级别</th><th>ID</th><th>类别</th><th>文件</th><th>行</th>
  <th>变量路径</th><th>消息</th><th>建议</th><th>状态</th>
</tr></thead>
<tbody>
{''.join(body_rows) if body_rows else '<tr><td colspan="9" style="text-align:center;color:#6a7180">无检查结果</td></tr>'}
</tbody>
</table>
<footer>由 MvuEjsLinter 生成 · 纯 Python EJS 静态检查工具</footer>
</body>
</html>
"""
    Path(path).write_text(doc, encoding="utf-8")
    return len(rows)
