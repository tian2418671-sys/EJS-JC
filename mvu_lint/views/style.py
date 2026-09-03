"""Application QSS stylesheet (dark theme)."""
from __future__ import annotations

STYLE_SHEET = """
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #1e2128;
}

QWidget {
    color: #d8dce4;
}

/* ── Drop zone ─────────────────────────────────────────── */
#DropZone {
    background-color: #262b34;
    border: 2px dashed #4a5160;
    border-radius: 10px;
    color: #8b93a3;
}
#DropZone[dragging="true"] {
    border-color: #4f9dff;
    background-color: #2c3340;
    color: #cfe3ff;
}

/* ── Group boxes ───────────────────────────────────────── */
QGroupBox {
    background-color: #262b34;
    border: 1px solid #343a45;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #a8b0c0;
}

/* ── Table ─────────────────────────────────────────────── */
QTableWidget {
    background-color: #22262e;
    alternate-background-color: #262b34;
    border: 1px solid #343a45;
    border-radius: 6px;
    gridline-color: #2e333d;
    selection-background-color: #2f4a7a;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #2b303a;
    color: #a8b0c0;
    border: none;
    border-right: 1px solid #343a45;
    border-bottom: 1px solid #343a45;
    padding: 5px 8px;
    font-weight: bold;
}
QTableWidget::item {
    padding: 3px 6px;
}
QTableWidget::item:selected {
    background-color: #2f4a7a;
}

/* ── Buttons ───────────────────────────────────────────── */
QPushButton {
    background-color: #2f3542;
    border: 1px solid #414958;
    border-radius: 6px;
    padding: 6px 14px;
    color: #d8dce4;
}
QPushButton:hover {
    background-color: #3a4150;
}
QPushButton:pressed {
    background-color: #262b34;
}
QPushButton:disabled {
    color: #6a7180;
    background-color: #272b33;
}
#PrimaryButton {
    background-color: #2d6fd6;
    border-color: #2d6fd6;
    color: #ffffff;
    font-weight: bold;
}
#PrimaryButton:hover {
    background-color: #3a7fe8;
}
#PrimaryButton:disabled {
    background-color: #274a80;
    border-color: #274a80;
    color: #9db8dd;
}

/* ── Combo / line edits ────────────────────────────────── */
QComboBox, QLineEdit {
    background-color: #2b303a;
    border: 1px solid #414958;
    border-radius: 6px;
    padding: 4px 8px;
    color: #d8dce4;
}
QComboBox QAbstractItemView {
    background-color: #2b303a;
    border: 1px solid #414958;
    selection-background-color: #2f4a7a;
}

/* ── Status bar / labels ───────────────────────────────── */
QStatusBar {
    background-color: #171a20;
    color: #8b93a3;
}
QStatusBar::item { border: none; }

QLabel#SectionTitle {
    color: #ffffff;
    font-size: 15px;
    font-weight: bold;
}
QLabel#MutedLabel {
    color: #8b93a3;
}
QLabel#WarningLabel {
    color: #e8b64c;
    background-color: #3a3220;
    border: 1px solid #6b5a24;
    border-radius: 6px;
    padding: 6px 10px;
}
QLabel#OkLabel {
    color: #6fd36f;
    background-color: #203a24;
    border: 1px solid #2f5c35;
    border-radius: 6px;
    padding: 6px 10px;
}

/* Level badges rendered as text — colors applied via foreground role
   in code so they survive re-sorting / filtering. */

QScrollBar:vertical {
    background: #22262e;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3a4150;
    border-radius: 6px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #22262e;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #3a4150;
    border-radius: 6px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QProgressBar {
    border: 1px solid #414958;
    border-radius: 6px;
    background-color: #2b303a;
    text-align: center;
    color: #d8dce4;
    min-height: 16px;
}
QProgressBar::chunk {
    background-color: #2d6fd6;
    border-radius: 5px;
}

QMenuBar {
    background-color: #171a20;
    color: #d8dce4;
}
QMenuBar::item:selected {
    background-color: #2f4a7a;
}
QMenu {
    background-color: #22262e;
    border: 1px solid #414958;
}
QMenu::item {
    padding: 5px 24px;
}
QMenu::item:selected {
    background-color: #2f4a7a;
}
"""