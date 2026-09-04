"""Simulation dialog — run the rule-driven simulator and inspect rounds/snapshots.

This is a Phase 3 / F4-F5 view.  It displays each simulation round, the
commands applied, and the variable snapshot at that point.  It is intentionally
simple: time-travel controls (slider, diff view) are Phase 4 enhancements.
"""
from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..controllers.app_controller import AppController


class SimulationWorker(QThread):
    """Run simulation off the UI thread."""

    progress = Signal(int, int)
    finished_ok = Signal(object)  # list[StepResult]
    failed = Signal(str)

    def __init__(self, controller: AppController, user_inputs: List[str],
                 max_steps: int = 20, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.user_inputs = user_inputs
        self.max_steps = max_steps

    def run(self):
        try:
            results = self.controller.run_simulation(
                user_inputs=self.user_inputs,
                max_steps=self.max_steps,
                progress_cb=self._on_progress,
            )
            self.finished_ok.emit(results)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(str(exc))

    def _on_progress(self, done: int, total: int):
        self.progress.emit(done, total)


class SimulationDialog(QDialog):
    """Modal dialog to run and inspect the rule-driven simulation."""

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._results = []
        self._worker: Optional[SimulationWorker] = None
        self._setup_ui()
        self.setWindowTitle("模拟对话运行（技术验证）")
        self.resize(900, 700)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.status_label = QLabel("点击下方按钮开始运行规则驱动的模拟对话。")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("▶ 运行模拟")
        self.run_btn.setToolTip("运行基于规则的变量推演（无 LLM）")
        self.run_btn.clicked.connect(self._on_run)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addLayout(btn_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Rounds table
        self.rounds_table = QTableWidget()
        self.rounds_table.setColumnCount(5)
        self.rounds_table.setHorizontalHeaderLabels(
            ["回合", "输入", "激活条目", "变更路径", "错误/警告"]
        )
        self.rounds_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.rounds_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.rounds_table.itemSelectionChanged.connect(self._on_round_selected)
        splitter.addWidget(self.rounds_table)

        # Details: commands + snapshot
        bottom = QSplitter(Qt.Orientation.Horizontal)
        self.commands_table = QTableWidget()
        self.commands_table.setColumnCount(7)
        self.commands_table.setHorizontalHeaderLabels(
            ["来源", "类型", "路径", "操作", "前值", "后值", "状态"]
        )
        self.commands_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.snapshot_text = QTextEdit()
        self.snapshot_text.setReadOnly(True)
        self.snapshot_text.setPlaceholderText("选择回合后显示变量快照…")
        bottom.addWidget(self.commands_table)
        bottom.addWidget(self.snapshot_text)
        splitter.addWidget(bottom)

        layout.addWidget(splitter, stretch=1)

    def _on_run(self):
        self.run_btn.setEnabled(False)
        self.status_label.setText("正在运行模拟…")
        self.progress.setRange(0, 20)
        self.progress.setValue(0)
        self.progress.setVisible(True)

        self._worker = SimulationWorker(self.controller, user_inputs=[])
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_finished(self, results):
        self._results = results
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText(f"模拟完成：共 {len(results)} 个回合。")
        self._populate_rounds(results)

    def _on_failed(self, message: str):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText("模拟运行失败")
        QMessageBox.critical(self, "模拟错误", message)

    def _populate_rounds(self, results):
        self.rounds_table.setRowCount(len(results))
        for i, r in enumerate(results):
            self.rounds_table.setItem(i, 0, QTableWidgetItem(str(r.round_number)))
            self.rounds_table.setItem(i, 1, QTableWidgetItem(r.user_input or "<无>"))
            self.rounds_table.setItem(i, 2, QTableWidgetItem(str(len(r.activated_entries))))
            self.rounds_table.setItem(i, 3, QTableWidgetItem(str(len(r.changed_paths))))
            self.rounds_table.setItem(i, 4, QTableWidgetItem(
                f"{len(r.errors)} / {len(r.warnings)}"
            ))

    def _on_round_selected(self):
        selected = self.rounds_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if row >= len(self._results):
            return
        result = self._results[row]

        self.commands_table.setRowCount(len(result.commands))
        for i, cmd in enumerate(result.commands):
            self.commands_table.setItem(i, 0, QTableWidgetItem(cmd.file_path))
            self.commands_table.setItem(i, 1, QTableWidgetItem(cmd.command_type))
            self.commands_table.setItem(i, 2, QTableWidgetItem(cmd.path))
            self.commands_table.setItem(i, 3, QTableWidgetItem(cmd.op))
            self.commands_table.setItem(i, 4, QTableWidgetItem(str(cmd.before)))
            self.commands_table.setItem(i, 5, QTableWidgetItem(str(cmd.after)))
            self.commands_table.setItem(i, 6, QTableWidgetItem(cmd.status))

        self.snapshot_text.setPlainText(
            json.dumps(result.snapshot, ensure_ascii=False, indent=2)
        )

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        event.accept()
