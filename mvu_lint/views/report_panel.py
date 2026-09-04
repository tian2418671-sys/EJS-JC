"""Report panel — errors table with level filter and summary."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_LEVEL_COLORS = {
    "Lv.1": QColor("#e5534b"),
    "Lv.2": QColor("#e8934a"),
    "Lv.3": QColor("#e8b64c"),
    "Lv.4": QColor("#6cb2e8"),
}

_HEADERS = ["级别", "ID", "类别", "文件", "行", "变量路径", "消息", "建议", "状态"]
_LEVELS = ["全部", "Lv.1", "Lv.2", "Lv.3", "Lv.4"]

_STATUS_LABELS = {
    "pending": "待处理",
    "fixed": "已修复",
    "ignored": "已忽略",
}


class ReportPanel(QWidget):
    """Displays static_errors rows with a level filter combo."""

    # Emitted when the user picks a new status from the context menu.
    status_changed = Signal(str, str)  # (error_id, new_status)
    # Emitted when the user requests an AI explanation from the context menu.
    explanation_requested = Signal(str)  # error_id

    def __init__(self, parent=None):
        super().__init__(parent)

        # Top bar: title + filter + summary
        top = QHBoxLayout()
        title = QLabel("检查报告")
        title.setObjectName("SectionTitle")
        self.summary_label = QLabel("尚未扫描")
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

        # Table
        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.cellDoubleClicked.connect(self._show_detail)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 52)
        header.resizeSection(1, 80)
        header.resizeSection(2, 56)
        header.resizeSection(4, 44)
        header.resizeSection(5, 180)
        header.resizeSection(8, 64)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

        # Internal state
        self._all_errors: List[dict] = []

    # ── Data ─────────────────────────────────────────────────────

    def show_errors(self, errors: List[dict], counts: Optional[dict] = None):
        """Replace report contents. counts: {"Lv.1": n, ...}."""
        self._all_errors = list(errors)
        self._update_summary(counts)
        self._apply_filter()

    def clear(self):
        self._all_errors = []
        self.summary_label.setText("尚未扫描")
        self.table.setRowCount(0)

    # ── Internals ────────────────────────────────────────────────

    def _update_summary(self, counts: Optional[dict]):
        if not counts:
            counts = {"Lv.1": 0, "Lv.2": 0, "Lv.3": 0, "Lv.4": 0}
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
        rows = [e for e in self._all_errors
                if level == "全部" or e.get("level") == level]
        self._fill_table(rows)

    def _fill_table(self, errors: List[dict]):
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)
        for row_idx, err in enumerate(errors):
            self.table.insertRow(row_idx)
            values = [
                err.get("level", ""),
                err.get("error_id", ""),
                err.get("category", ""),
                err.get("file_path", ""),
                "" if err.get("line_number") is None else str(err["line_number"]),
                err.get("path") or "",
                err.get("message", ""),
                err.get("suggestion") or "",
                _STATUS_LABELS.get(err.get("status", ""), err.get("status", "")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    lv_color = _LEVEL_COLORS.get(value)
                    if lv_color:
                        item.setForeground(lv_color)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 8:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

    def _show_detail(self, row: int, _col: int):
        if row < 0 or row >= self.table.rowCount():
            return
        level = self.table.item(row, 0).text()
        error_id = self.table.item(row, 1).text()
        file_path = self.table.item(row, 3).text()
        line = self.table.item(row, 4).text()
        path = self.table.item(row, 5).text()
        message = self.table.item(row, 6).text()
        suggestion = self.table.item(row, 7).text()

        body = (
            f"级别: {level}\n"
            f"ID: {error_id}\n"
            f"文件: {file_path}"
            + (f" : 第 {line} 行" if line else "")
            + (f"\n变量路径: {path}" if path else "")
            + f"\n\n消息:\n{message}"
            + (f"\n\n建议:\n{suggestion}" if suggestion else "")
        )
        QMessageBox.information(self, f"错误详情 — {error_id}", body)

    # ── Status management (context menu) ────────────────────────

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        error_id = self.table.item(row, 1).text()

        menu = QMenu(self)
        explain_action = menu.addAction("🤖 AI 解释")
        explain_action.triggered.connect(
            lambda checked=False, eid=error_id: self.explanation_requested.emit(eid)
        )
        menu.addSeparator()
        for status, label in _STATUS_LABELS.items():
            action = menu.addAction(f"标记为「{label}」")
            action.triggered.connect(
                lambda checked=False, s=status, eid=error_id: self.status_changed.emit(eid, s)
            )
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def update_status(self, error_id: str, status: str):
        """Update the in-memory status of one error and refresh the table."""
        for err in self._all_errors:
            if err.get("error_id") == error_id:
                err["status"] = status
                break
        self._apply_filter()