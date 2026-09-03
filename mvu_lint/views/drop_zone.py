"""Drop zone widget — accept ZIP drag & drop or click-to-browse."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QVBoxLayout, QLabel


class DropZone(QFrame):
    """A dashed-border area that accepts a role-card .zip file.

    Signals:
        file_selected(str): emitted with an absolute zip path once a
            valid archive is provided (drop or file dialog).
    """

    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("📦 拖入角色卡 ZIP 到此处")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.hint_label = QLabel("或点击此处选择文件\n（支持 .zip 角色卡包）")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("color: #8b93a3;")

        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

    # ── Mouse: click to browse ──────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse()
        super().mousePressEvent(event)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择角色卡 ZIP", "",
            "ZIP 压缩包 (*.zip);;所有文件 (*.*)",
        )
        if path:
            self.file_selected.emit(path)

    # ── Drag & drop ─────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self._clear_drag_state()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._clear_drag_state()
        if not self._accepts(event):
            event.ignore()
            return
        path = event.mimeData().urls()[0].toLocalFile()
        event.acceptProposedAction()
        if path:
            self.file_selected.emit(path)

    def _accepts(self, event) -> bool:
        if not event.mimeData().hasUrls():
            return False
        urls = event.mimeData().urls()
        if not urls:
            return False
        suffix = Path(urls[0].toLocalFile()).suffix.lower()
        return suffix == ".zip"

    def _clear_drag_state(self):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    # ── Status text ─────────────────────────────────────────────

    def set_loaded(self, display_name: str):
        """Switch the zone into 'loaded project' look."""
        self.title_label.setText("✅ 已加载项目")
        self.hint_label.setText(
            f"{display_name}\n再次拖入 / 点击可更换角色卡"
        )
        self.setProperty("dragging", False)

    def reset(self):
        self.title_label.setText("📦 拖入角色卡 ZIP 到此处")
        self.hint_label.setText("或点击此处选择文件\n（支持 .zip 角色卡包）")