"""Dynamic findings dialog (Phase 4 / F6) — side-by-side with static report.

Shows the rule-based dynamic locator results in the same table style as the
static report panel, with per-finding status management (pending / fixed /
ignored).  The findings come from ``dynamic_findings`` and are rendered
alongside (not mixed into) the static error table.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_LEVEL_COLORS = {
    "Lv.1": QColor("#e5534b"),
    "Lv.2": QColor("#e8934a"),
    "Lv.3": QColor("#e8b64c"),
    "Lv.4": QColor("#6cb2e8"),
}
_HEADERS = ["级别", "ID", "回合", "文件", "变量路径", "消息", "建议", "状态"]
_LEVELS = ["全部", "Lv.1", "Lv.2", "Lv.3", "Lv.4"]
_STATUS_LABELS = {
    "pending": "待处理",
    "fixed": "已修复",
    "ignored": "已忽略",
}


class DynamicFindingsDialog(QDialog):
    """Modal dialog listing dynamic locator findings."""

    # Emitted when the user picks a new status from the context menu.
    status_changed = Signal(str, str)  # (finding_id, new_status)

    def __init__(self, controller, findings: Optional[List[dict]] = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._all: List[dict] = list(findings) if findings is not None else []
        self._setup_ui()
        self.setWindowTitle("动态定位结果（与静态报告并列）")
        self.resize(1000, 560)
        self._populate()

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        title = QLabel("动态定位 — 基于运行日志 + 快照 diff")
        title.setObjectName("SectionTitle")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("MutedLabel")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(_LEVELS)
        self.filter_combo.setMaximumWidth(110)
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.summary_label)
        top.addSpacing(12)
        top.addWidget(self.filter_combo)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._show_detail)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 52)
        header.resizeSection(1, 90)
        header.resizeSection(2, 56)
        header.resizeSection(3, 170)
        header.resizeSection(4, 180)
        header.resizeSection(7, 64)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("重新运行定位")
        self.refresh_btn.setToolTip("基于最新模拟数据重新执行动态定位器")
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    # ── data ────────────────────────────────────────────────────────

    def _on_refresh(self):
        try:
            self._all = self.controller.run_dynamic_analysis()
        except Exception as exc:  # pragma: no cover - defensive
            QMessageBox.critical(self, "动态定位失败", str(exc))
            return
        self.status_changed.emit("", "")
        self._populate()

    def _populate(self):
        self._update_summary()
        self._apply_filter()

    # ── internals ───────────────────────────────────────────────────

    def _update_summary(self):
        counts = {"Lv.1": 0, "Lv.2": 0, "Lv.3": 0, "Lv.4": 0}
        for f in self._all:
            counts[f.get("level", "Lv.3")] = counts.get(f.get("level", "Lv.3"), 0) + 1
        parts = []
        for lv in ("Lv.1", "Lv.2", "Lv.3", "Lv.4"):
            n = counts.get(lv, 0)
            color = _LEVEL_COLORS[lv].name()
            parts.append(f'<span style="color:{color}">{lv}: {n}</span>')
        total = sum(counts.values())
        self.summary_label.setText(
            f"共 {total} 条　" + "　".join(parts)
        )
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)

    def _apply_filter(self, _extra: Optional[str] = None):
        level = self.filter_combo.currentText()
        rows = [f for f in self._all
                if level == "全部" or f.get("level") == level]
        self._fill_table(rows)

    def _fill_table(self, findings: List[dict]):
        self.table.setRowCount(0)
        for row_idx, f in enumerate(findings):
            self.table.insertRow(row_idx)
            values = [
                f.get("level", ""),
                f.get("error_id", ""),
                "" if f.get("round_number") is None else str(f["round_number"]),
                f.get("file_path", ""),
                f.get("path") or "",
                f.get("message", ""),
                f.get("suggestion") or "",
                _STATUS_LABELS.get(f.get("status", ""), f.get("status", "")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    lv_color = _LEVEL_COLORS.get(value)
                    if lv_color:
                        item.setForeground(lv_color)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col in (2, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

    def _show_detail(self, row: int, _col: int):
        if row < 0 or row >= self.table.rowCount():
            return
        values = [self.table.item(row, c).text() if self.table.item(row, c) else ""
                  for c in range(len(_HEADERS))]
        level, fid, round_no, file_path, path, message, suggestion, _st = values
        body = (
            f"级别: {level}\n"
            f"ID: {fid}\n"
            + (f"回合: {round_no}\n" if round_no else "")
            + (f"文件: {file_path}\n" if file_path else "")
            + (f"变量路径: {path}\n" if path else "")
            + f"\n消息:\n{message}"
            + (f"\n\n建议:\n{suggestion}" if suggestion else "")
        )
        QMessageBox.information(self, f"动态定位详情 — {fid}", body)

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        finding_id = self.table.item(row, 1).text()
        menu = QMenu(self)
        for status, label in _STATUS_LABELS.items():
            action = menu.addAction(f"标记为「{label}」")
            action.triggered.connect(
                lambda checked=False, s=status, fid=finding_id:
                    self.status_changed.emit(fid, s)
            )
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def update_status(self, finding_id: str, status: str):
        """Update the in-memory status of one finding and refresh."""
        for f in self._all:
            if f.get("error_id") == finding_id:
                f["status"] = status
                break
        self._apply_filter()
