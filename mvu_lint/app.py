"""GUI entry point: python -m mvu_lint gui  (or python -m mvu_lint.app)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .views.main_window import MainWindow
from .views.style import STYLE_SHEET


def _resource_path(name: str) -> str:
    """Locate a bundled resource (works both dev and PyInstaller frozen)."""
    if getattr(sys, "frozen", False):  # PyInstaller onefile
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return str(base / "resources" / name)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MVU + EJS 智能检查工具")
    app.setOrganizationName("MvuEjsLinter")
    app.setStyleSheet(STYLE_SHEET)

    icon_path = _resource_path("icon.png")
    if Path(icon_path).exists():
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())