"""GUI entry point: python -m mvu_lint gui  (or python -m mvu_lint.app)."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .views.main_window import MainWindow
from .views.style import STYLE_SHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MVU + EJS 智能检查工具")
    app.setOrganizationName("MvuEjsLinter")
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())