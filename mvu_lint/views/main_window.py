"""Main window — menu bar, drop zone, project info, report panel."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..controllers.app_controller import AppController, ScanSummary
from ..controllers.scan_worker import ScanWorker
from ..utils.report_exporter import export_csv, export_html, export_markdown
from .drop_zone import DropZone
from .dynamic_report_dialog import DynamicFindingsDialog
from .report_panel import ReportPanel
from .simulation_dialog import SimulationDialog
from .time_travel_dialog import TimeTravelDialog

_MAX_RECENT = 5
_SETTINGS_ORG = "MvuEjsLinter"


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()
        self.controller = AppController()
        self.worker: ScanWorker | None = None
        self.settings = QSettings(_SETTINGS_ORG, _SETTINGS_ORG)

        self.setWindowTitle("MVU + EJS 智能检查工具")
        self.resize(1240, 780)

        self._build_ui()
        self._connect_actions()
        self._refresh_recent_menu()
        self.statusBar().showMessage("就绪 — 拖入角色卡（.png / .json）开始")

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        # Menus
        file_menu = self.menuBar().addMenu("文件(&F)")
        self.action_open = QAction("打开角色卡…", self)
        self.action_open.setShortcut("Ctrl+O")
        self.action_quit = QAction("退出", self)
        self.action_quit.setShortcut("Ctrl+Q")
        file_menu.addAction(self.action_open)

        # Recent files submenu
        self.recent_menu = QMenu("最近打开", self)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()

        # Export submenu
        export_menu = QMenu("导出报告", self)
        self.action_export_html = QAction("导出 HTML…", self)
        self.action_export_csv = QAction("导出 CSV…", self)
        self.action_export_md = QAction("导出 Markdown…", self)
        export_menu.addAction(self.action_export_html)
        export_menu.addAction(self.action_export_csv)
        export_menu.addAction(self.action_export_md)
        file_menu.addMenu(export_menu)

        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        check_menu = self.menuBar().addMenu("检查(&C)")
        self.action_scan = QAction("开始静态检查", self)
        self.action_scan.setShortcut("F5")
        self.action_clear = QAction("清空报告", self)
        check_menu.addAction(self.action_scan)
        check_menu.addAction(self.action_clear)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        self.action_about = QAction("关于", self)
        help_menu.addAction(self.action_about)

        # Central splitter
        central = QWidget()
        splitter = QSplitter(Qt.Orientation.Horizontal, central)

        # Left pane: drop zone + project info
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.drop_zone = DropZone()
        left_layout.addWidget(self.drop_zone)

        info_box = QGroupBox("项目信息")
        info_layout = QVBoxLayout(info_box)
        self.info_schema_label = QLabel("Schema: —")
        self.info_schema_label.setObjectName("MutedLabel")
        self.info_folder_label = QLabel("文件数: —")
        self.info_folder_label.setObjectName("MutedLabel")
        self.schema_status_label = QLabel("尚未导入项目")
        info_layout.addWidget(self.info_schema_label)
        info_layout.addWidget(self.info_folder_label)
        info_layout.addWidget(self.schema_status_label)
        left_layout.addWidget(info_box)

        # Scan summary box
        scan_box = QGroupBox("最近一次扫描")
        scan_layout = QVBoxLayout(scan_box)
        self.scan_summary_label = QLabel("—")
        self.scan_summary_label.setObjectName("MutedLabel")
        self.scan_summary_label.setWordWrap(True)
        scan_layout.addWidget(self.scan_summary_label)
        left_layout.addWidget(scan_box)

        self.scan_button = QPushButton("开始静态检查 (F5)")
        self.scan_button.setObjectName("PrimaryButton")
        self.scan_button.setEnabled(False)
        left_layout.addWidget(self.scan_button)

        self.simulate_button = QPushButton("运行模拟（技术验证）")
        self.simulate_button.setEnabled(False)
        self.simulate_button.clicked.connect(self._on_simulate)
        left_layout.addWidget(self.simulate_button)

        self.timetravel_button = QPushButton("时间旅行 — 快照回放")
        self.timetravel_button.setEnabled(False)
        self.timetravel_button.setToolTip("滑块按步回退/前进，查看任意步骤变量状态")
        self.timetravel_button.clicked.connect(self._on_time_travel)
        left_layout.addWidget(self.timetravel_button)

        self.dynamic_button = QPushButton("动态定位（基于日志 + 快照）")
        self.dynamic_button.setEnabled(False)
        self.dynamic_button.setToolTip("结合模拟日志与快照 diff 定位变量异常变更点")
        self.dynamic_button.clicked.connect(self._on_dynamic)
        left_layout.addWidget(self.dynamic_button)

        left_layout.addStretch(1)

        # Right pane: report
        self.report_panel = ReportPanel()

        splitter.addWidget(left)
        splitter.addWidget(self.report_panel)
        splitter.setSizes([340, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        # Status bar progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

    def _connect_actions(self):
        self.action_open.triggered.connect(self._browse_card)
        self.action_quit.triggered.connect(self.close)
        self.action_scan.triggered.connect(self._start_scan)
        self.action_clear.triggered.connect(self._clear_report)
        self.action_about.triggered.connect(self._show_about)
        self.action_export_html.triggered.connect(lambda: self._export_report("html"))
        self.action_export_csv.triggered.connect(lambda: self._export_report("csv"))
        self.action_export_md.triggered.connect(lambda: self._export_report("md"))
        self.drop_zone.file_selected.connect(self.import_card)
        self.scan_button.clicked.connect(self._start_scan)
        self.simulate_button.clicked.connect(self._on_simulate)
        self.timetravel_button.clicked.connect(self._on_time_travel)
        self.dynamic_button.clicked.connect(self._on_dynamic)
        self.report_panel.status_changed.connect(self._on_status_changed)

    # ── Import ────────────────────────────────────────────────────

    def _browse_card(self):
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "打开角色卡", "",
            "角色卡 (*.png *.json);;PNG 角色卡 (*.png);;JSON 角色卡 (*.json);;所有文件 (*.*)",
        )
        if path:
            self.import_card(path)

    def import_card(self, card_path: str):
        try:
            self.statusBar().showMessage(f"正在导入: {Path(card_path).name}…")
            project = self.controller.import_card(card_path)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", f"无法导入角色卡:\n{exc}")
            self.statusBar().showMessage("导入失败")
            self.simulate_button.setEnabled(False)
            self.timetravel_button.setEnabled(False)
            self.dynamic_button.setEnabled(False)
            return

        self.drop_zone.set_loaded(Path(card_path).name)
        self.info_folder_label.setText(
            f"检查块数: {len(project.files)}　来源: {Path(card_path).name}"
        )

        schema_form = project.schema_form or "未找到"
        self.info_schema_label.setText(f"Schema: {schema_form}")

        if self.controller.schema_info is not None:
            self.schema_status_label.setObjectName("OkLabel")
            self.schema_status_label.setText(
                f"✅ 变量初始值解析成功（{len(self.controller.schema_info.paths)} 条路径）"
            )
        else:
            self.schema_status_label.setObjectName("WarningLabel")
            reason = self.controller.degraded_reason()
            self.schema_status_label.setText(
                f"⚠️ 部分 MVU 检查已降级，角色卡缺少「# 变量初始值」块"
                + (f"\n{reason}" if reason else "")
            )
        # Object names need re-polishing to apply style changes
        self.schema_status_label.style().unpolish(self.schema_status_label)
        self.schema_status_label.style().polish(self.schema_status_label)

        self.report_panel.clear()
        self.scan_summary_label.setText("—")
        self.scan_button.setEnabled(True)
        self.simulate_button.setEnabled(True)
        self.timetravel_button.setEnabled(False)
        self.dynamic_button.setEnabled(False)
        self._record_recent(card_path)
        self.statusBar().showMessage(f"导入完成: {Path(card_path).name} — 点击「开始静态检查」")

    # ── Scan ──────────────────────────────────────────────────────

    def _start_scan(self):
        if self.worker and self.worker.isRunning():
            return

        self.scan_button.setEnabled(False)
        self.action_scan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(1, len(self.controller.project.files)))
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("正在静态检查…")

        self.worker = ScanWorker(self.controller, self)
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished_ok.connect(self._on_scan_done)
        self.worker.failed.connect(self._on_scan_failed)
        # Order matters: drop the Python reference first, then let Qt
        # delete the C++ object. Keeps self.worker valid while signals
        # are still being delivered.
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_worker_finished(self):
        self.worker = None

    def _on_scan_progress(self, done: int, total: int):
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(done)
        self.statusBar().showMessage(f"静态检查中… {done}/{total}")

    def _on_scan_done(self, summary: ScanSummary):
        self._scan_finished_common()
        counts = self.controller.get_counts()
        self.report_panel.show_errors(
            self.controller.get_errors(), counts=counts
        )

        schema_txt = (
            f"schema: {summary.schema_form or '无'}"
            + (f"（{summary.schema_path_count} 条路径）" if summary.schema_path_count else "")
        )
        self.scan_summary_label.setText(
            f"扫描文件: {summary.files_scanned}/{summary.total_files}\n"
            f"错误: {summary.errors_inserted}\n"
            f"{schema_txt}"
            + ("\n⚠️ 已降级模式" if summary.degraded else "")
        )
        if summary.degraded:
            self.statusBar().showMessage(
                "检查完成（降级模式） — " + summary.degraded_reason
            )
        else:
            self.statusBar().showMessage("检查完成")

    def _on_scan_failed(self, message: str):
        self._scan_finished_common()
        QMessageBox.critical(self, "检查失败", message)
        self.statusBar().showMessage("检查失败")

    def _on_simulate(self):
        if not self.controller.has_project():
            QMessageBox.warning(self, "未导入项目", "请先导入角色卡。")
            return
        dialog = SimulationDialog(self.controller, parent=self)
        dialog.exec()
        # After a simulation run, time-travel + dynamic analysis become useful.
        self.timetravel_button.setEnabled(True)
        self.dynamic_button.setEnabled(True)

    def _on_time_travel(self):
        if not self.controller.get_simulation_rounds():
            QMessageBox.information(
                self, "时间旅行", "请先运行一次模拟（「运行模拟」按钮），再回放快照。"
            )
            return
        dialog = TimeTravelDialog(self.controller, parent=self)
        dialog.exec()

    def _on_dynamic(self):
        if not self.controller.get_simulation_rounds():
            QMessageBox.information(
                self, "动态定位", "请先运行一次模拟，动态定位需要模拟日志与快照数据。"
            )
            return
        findings = self.controller.run_dynamic_analysis()
        dialog = DynamicFindingsDialog(
            self.controller, findings=findings, parent=self
        )
        dialog.status_changed.connect(self._on_dynamic_status_changed)
        dialog.exec()

    def _on_dynamic_status_changed(self, finding_id: str, status: str):
        if not finding_id:
            return
        if self.controller.set_dynamic_status(finding_id, status):
            self.statusBar().showMessage(f"{finding_id} 已标记为 {status}")

    def _scan_finished_common(self):
        self.scan_button.setEnabled(True)
        self.action_scan.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _clear_report(self):
        if self.worker and self.worker.isRunning():
            return
        self.controller.clear_errors()
        self.report_panel.clear()
        self.scan_summary_label.setText("—")
        self.statusBar().showMessage("报告已清空")

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 MVU + EJS 智能检查工具",
            "MVU + EJS 智能代码检查工具\n\n"
            "版本: v0.4 (Phase 4)\n\n"
            "功能:\n"
            "• 导入角色卡（PNG/JSON）并建立检查块索引\n"
            "• 纯 Python EJS 静态检查（Lv.1–Lv.4）\n"
            "• MVU 命令 / JSON Patch / schema 联动 / 自动修复\n"
            "• 规则驱动模拟对话（技术验证）\n"
            "• 时间旅行快照回放 + 动态定位器\n"
            "• SQLite 持久化错误报告\n\n"
            "技术栈: PySide6 + SQLite + llama-cpp-python(可选)",
        )

    # ── Export / recent files / status ──────────────────────────

    def _export_report(self, fmt: str):
        errors = self.controller.get_errors()
        if not errors:
            QMessageBox.information(self, "导出报告", "当前没有可导出的检查结果。")
            return

        from PySide6.QtWidgets import QFileDialog

        exts = {
            "html": "HTML 文件 (*.html)",
            "csv": "CSV 文件 (*.csv)",
            "md": "Markdown 文件 (*.md)",
        }
        default_name = f"检查报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "导出报告", default_name, exts[fmt])
        if not path:
            return

        project = self.controller.project
        try:
            if fmt == "html":
                export_html(
                    errors, path,
                    project_name=Path(project.source).name if project else "",
                    schema_form=project.schema_form if project else "",
                    degraded=self.controller.schema_info is None,
                    counts=self.controller.get_counts(),
                )
            elif fmt == "csv":
                export_csv(errors, path)
            else:
                export_markdown(errors, path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"无法写入报告:\n{exc}")
            return
        self.statusBar().showMessage(f"报告已导出: {Path(path).name}")

    def _on_status_changed(self, error_id: str, status: str):
        if self.controller.set_error_status(error_id, status):
            self.report_panel.update_status(error_id, status)
            self.statusBar().showMessage(f"{error_id} 已标记为 {status}")

    def _record_recent(self, card_path: str):
        key = str(Path(card_path).resolve())
        recents = list(self.settings.value("recent_files", [], type=list) or [])
        recents = [p for p in recents if p != key]
        recents.insert(0, key)
        self.settings.setValue("recent_files", recents[:_MAX_RECENT])
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self.recent_menu.clear()
        recents = list(self.settings.value("recent_files", [], type=list) or [])
        recents = [p for p in recents if Path(p).exists()]
        if not recents:
            empty = QAction("（暂无）", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for p in recents:
            action = QAction(Path(p).name, self)
            action.setToolTip(p)
            action.triggered.connect(lambda checked=False, path=p: self.import_card(path))
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        clear_action = QAction("清空列表", self)
        clear_action.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_action)

    def _clear_recent(self):
        self.settings.remove("recent_files")
        self._refresh_recent_menu()

    # ── Lifecycle ─────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.worker is not None:
            try:
                self.worker.requestInterruption()
                self.worker.wait(2000)
            except RuntimeError:
                pass  # worker already finished and was cleaned up
        self.controller.close()
        super().closeEvent(event)