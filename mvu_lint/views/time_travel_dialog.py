"""Time-travel dialog (Phase 4 / F5) — replay simulation snapshots.

A slider walks the persisted variable snapshots step by step.  Each step
shows the flattened variable table (rows that changed since the previous
step are highlighted) plus the command log for that round, so the user can
pinpoint *when* a variable went wrong.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..controllers.app_controller import AppController
from ..core.debugger import _flatten

_CHANGED_BG = "#3a2f1f"   # subtle amber background for changed rows


class TimeTravelDialog(QDialog):
    """Modal dialog: replay variable state snapshots via a slider."""

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._steps: List[dict] = []      # [{label, flat, raw, changed, logs}]
        self._current = 0
        self._setup_ui()
        self.setWindowTitle("时间旅行 — 快照回放")
        self.resize(960, 660)
        self._load_steps()

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Slider row
        slider_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀ 上一步")
        self.next_btn = QPushButton("下一步 ▶")
        self.step_label = QLabel("—")
        self.step_label.setObjectName("MutedLabel")
        self.prev_btn.clicked.connect(self._go_prev)
        self.next_btn.clicked.connect(self._go_next)
        slider_row.addWidget(self.prev_btn)
        slider_row.addWidget(self.next_btn)
        slider_row.addStretch(1)
        slider_row.addWidget(self.step_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        layout.addLayout(slider_row)
        layout.addWidget(self.slider)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: flattened variable table
        self.var_table = QTableWidget()
        self.var_table.setColumnCount(3)
        self.var_table.setHorizontalHeaderLabels(["变量路径", "值", "变更"])
        self.var_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.var_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.var_table.horizontalHeader().resizeSection(0, 260)
        self.var_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.var_table.setAlternatingRowColors(True)
        splitter.addWidget(self.var_table)

        # Right: raw snapshot + command log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setPlaceholderText("变更路径与命令日志…")
        right_layout.addWidget(self.diff_text, stretch=3)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setPlaceholderText("完整快照 JSON…")
        right_layout.addWidget(self.raw_text, stretch=2)
        splitter.addWidget(right)

        splitter.setSizes([480, 480])
        layout.addWidget(splitter, stretch=1)

    # ── data loading ────────────────────────────────────────────────

    def _load_steps(self):
        """Build steps: [initial state] + [snapshot after each round]."""
        rounds = self.controller.get_simulation_rounds()
        snapshots = self.controller.get_state_snapshots()
        logs = self.controller.get_simulation_logs()

        logs_by_round: Dict[int, List[dict]] = {}
        for log in logs:
            logs_by_round.setdefault(log["round_id"], []).append(log)

        round_by_id = {r["id"]: r for r in rounds}

        # Step 0: initial state from the card's initvar block
        initial: Dict[str, Any] = {}
        if self.controller.project and self.controller.project.card is not None:
            try:
                from ..core.card_loader import extract_schema_dict
                initial = extract_schema_dict(self.controller.project.card) or {}
            except Exception:
                initial = {}
        self._steps.append({
            "label": "初始状态",
            "flat": _flatten(initial),
            "raw": initial,
            "changed": [],
            "logs": [],
        })

        for snap in sorted(snapshots, key=lambda s: s["id"]):
            try:
                raw = json.loads(snap.get("stat_data") or "{}")
            except (json.JSONDecodeError, TypeError):
                raw = {}
            try:
                changed = json.loads(snap.get("changed_paths") or "[]")
            except (json.JSONDecodeError, TypeError):
                changed = []
            round_no = round_by_id.get(snap["round_id"], {}).get("round_number", "")
            self._steps.append({
                "label": f"第 {round_no} 轮后",
                "flat": _flatten(raw),
                "raw": raw,
                "changed": changed,
                "logs": logs_by_round.get(snap["round_id"], []),
            })

        self.slider.setMaximum(max(0, len(self._steps) - 1))
        self.slider.setValue(0)
        self._render_step(0)

    # ── navigation ──────────────────────────────────────────────────

    def _go_prev(self):
        if self._current > 0:
            self.slider.setValue(self._current - 1)

    def _go_next(self):
        if self._current < len(self._steps) - 1:
            self.slider.setValue(self._current + 1)

    def _on_slider(self, value: int):
        self._render_step(value)

    # ── rendering ───────────────────────────────────────────────────

    def _render_step(self, index: int):
        if index < 0 or index >= len(self._steps):
            return
        self._current = index
        step = self._steps[index]

        self.step_label.setText(
            f"{step['label']}　（{index + 1}/{len(self._steps)}）"
        )
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self._steps) - 1)

        prev_flat = self._steps[index - 1]["flat"] if index > 0 else {}
        cur_flat = step["flat"]

        keys = sorted(set(prev_flat) | set(cur_flat))
        self.var_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            old = prev_flat.get(key, "<未定义>")
            new = cur_flat.get(key, "<未定义>")
            changed = index > 0 and old != new

            path_item = QTableWidgetItem(key)
            val_item = QTableWidgetItem(
                json.dumps(new, ensure_ascii=False) if not isinstance(new, str)
                else new
            )
            mark_item = QTableWidgetItem("▲" if changed else "")
            if changed:
                for item in (path_item, val_item, mark_item):
                    item.setBackground(QColor(_CHANGED_BG))
            if key in step["changed"]:
                mark_item.setText("▲ 变更")
            self.var_table.setItem(row, 0, path_item)
            self.var_table.setItem(row, 1, val_item)
            self.var_table.setItem(row, 2, mark_item)

        # Diff + command log panel
        parts: List[str] = []
        if index > 0:
            diffs = [(k, prev_flat.get(k, "<未定义>"), cur_flat.get(k, "<未定义>"))
                     for k in keys if prev_flat.get(k) != cur_flat.get(k)]
            if diffs:
                parts.append("── 本步变更 ──")
                for k, old, new in diffs:
                    parts.append(
                        f"• {k}\n    {old!r}  →  {new!r}"
                    )
            else:
                parts.append("本步无变量变更。")
        else:
            parts.append("初始状态（来自角色卡「# 变量初始值」块）。")

        if step["logs"]:
            parts.append("")
            parts.append("── 本步命令日志 ──")
            for log in step["logs"]:
                status = log.get("status", "")
                line = (
                    f"• [{status}] {log.get('command_type', '')} "
                    f"{log.get('path', '')} {log.get('op', '')}"
                )
                if log.get("before_value") is not None or log.get("after_value") is not None:
                    line += (
                        f"　{log.get('before_value', '—')} → {log.get('after_value', '—')}"
                    )
                if log.get("error"):
                    line += f"　⚠ {log.get('error')}"
                parts.append(line)
        else:
            parts.append("")
            parts.append("本步无命令执行。")

        self.diff_text.setPlainText("\n".join(parts))
        self.raw_text.setPlainText(
            json.dumps(step["raw"], ensure_ascii=False, indent=2)
        )
