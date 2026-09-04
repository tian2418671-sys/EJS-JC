"""AI explanation dialog (Phase 5 / F7) — show a root-cause explanation.

Generates the explanation on a background thread (so the UI never blocks on a
slow local model) and displays the result together with its provenance
(LLM vs. template) and the knowledge chunks that informed it.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..controllers.app_controller import AppController

_SOURCE_LABELS = {
    "llm": "🤖 由本地模型生成",
    "template": "📄 由模板规则生成（未加载 LLM 模型）",
}


class ExplanationWorker(QThread):
    """Generate an explanation off the UI thread."""

    finished_ok = Signal(object)   # ExplanationResult.to_dict()
    failed = Signal(str)

    def __init__(self, controller: AppController, error_id: str,
                 timeout: float = 60.0, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.error_id = error_id
        self.timeout = timeout

    def run(self):
        try:
            result = self.controller.explain_error(
                self.error_id, use_llm=True, timeout=self.timeout
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(str(exc))


class ExplanationDialog(QDialog):
    """Modal dialog showing the explanation for one error."""

    def __init__(self, controller: AppController, error: dict, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.error = error
        self._worker: Optional[ExplanationWorker] = None

        self._setup_ui()
        self.setWindowTitle(f"AI 解释 — {error.get('error_id', '')}")
        self.resize(760, 560)
        self._start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("错误解释")
        title.setObjectName("SectionTitle")
        self.source_label = QLabel("正在生成…")
        self.source_label.setObjectName("MutedLabel")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.source_label)
        layout.addLayout(header)

        self.error_summary = QLabel(self._error_summary_text())
        self.error_summary.setObjectName("MutedLabel")
        self.error_summary.setWordWrap(True)
        layout.addWidget(self.error_summary)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("正在分析错误，请稍候…")
        layout.addWidget(self.text, stretch=1)

        self.chunks_label = QLabel("")
        self.chunks_label.setObjectName("MutedLabel")
        self.chunks_label.setWordWrap(True)
        layout.addWidget(self.chunks_label)

        btn = QHBoxLayout()
        self.retry_btn = QPushButton("重新生成")
        self.retry_btn.clicked.connect(self._start)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn.addWidget(self.retry_btn)
        btn.addStretch(1)
        btn.addWidget(self.close_btn)
        layout.addLayout(btn)

    def _error_summary_text(self) -> str:
        e = self.error
        parts = [f"级别: {e.get('level', '')}　类别: {e.get('category', '')}"]
        if e.get("file_path"):
            parts.append(f"文件: {e['file_path']}")
        if e.get("path"):
            parts.append(f"变量路径: {e['path']}")
        return "　".join(parts)

    def _start(self):
        self.retry_btn.setEnabled(False)
        self.source_label.setText("正在生成…")
        self.text.setPlainText("")
        self.chunks_label.setText("")

        self._worker = ExplanationWorker(
            self.controller, self.error.get("error_id", "")
        )
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_worker_finished(self):
        self._worker = None

    def _on_finished(self, result):
        self.retry_btn.setEnabled(True)
        if not result:
            self.source_label.setText("未能生成解释")
            self.text.setPlainText("未找到该错误记录。")
            return
        self.source_label.setText(
            _SOURCE_LABELS.get(result.get("source", ""), result.get("source", ""))
        )
        self.text.setPlainText(result.get("explanation", ""))

        chunks = result.get("chunks") or []
        if chunks:
            titles = "、".join(c.get("title", "") for c in chunks)
            self.chunks_label.setText(f"参考知识: {titles}")
        else:
            self.chunks_label.setText("")

    def _on_failed(self, message: str):
        self.retry_btn.setEnabled(True)
        self.source_label.setText("生成失败")
        self.text.setPlainText(f"解释生成失败：\n{message}")
        QMessageBox.warning(self, "解释失败", message)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        event.accept()
