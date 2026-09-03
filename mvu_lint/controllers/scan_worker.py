"""QThread wrapper for running static checks off the UI thread."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..controllers.app_controller import AppController, ScanSummary


class ScanWorker(QThread):
    """Runs AppController.run_static_check in a background thread."""

    progress = Signal(int, int)      # (files_done, files_total)
    finished_ok = Signal(object)     # ScanSummary
    failed = Signal(str)

    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller

    def run(self):
        try:
            summary = self.controller.run_static_check(
                progress_cb=self._on_progress
            )
            self.finished_ok.emit(summary)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(str(exc))

    def _on_progress(self, done: int, total: int):
        self.progress.emit(done, total)