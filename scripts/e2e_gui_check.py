"""End-to-end GUI pipeline check — runs the real ScanWorker in an event loop.

Usage: python scripts/e2e_gui_check.py [角色卡.zip]
Exit code 0 → import + threaded scan + report refresh all succeeded.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mvu_lint.views.main_window import MainWindow  # noqa: E402

RESULTS = {}


def run(zip_path: str) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()

    def watchdog():
        print("[WATCHDOG] 10 秒超时 — 事件循环未正常退出")
        print("  窗口标题:", window.windowTitle())
        print("  状态栏:", window.statusBar().currentMessage())
        print("  表格行数:", window.report_panel.table.rowCount())
        print("  worker running:", bool(window.worker and window.worker.isRunning()))
        window.close()
        app.exit(2)

    QTimer.singleShot(10000, watchdog)

    def step_import():
        print(f"[1/3] 导入 {Path(zip_path).name}…", flush=True)
        try:
            window.import_zip(zip_path)
        except Exception:
            traceback.print_exc()
            app.exit(3)
            return
        assert window.scan_button.isEnabled(), "扫描按钮应已启用"
        print("      schema 状态:", window.schema_status_label.text()[:60], flush=True)
        RESULTS["schema_text"] = window.schema_status_label.text()
        window._start_scan()
        print("      扫描线程已启动", flush=True)

    def step_wait_worker():
        if window.worker and window.worker.isRunning():
            QTimer.singleShot(50, step_wait_worker)
            return
        # Worker finished (or was cleaned up): signals were delivered in
        # order, so the report table is already refreshed at this point.
        print("[2/3] 后台扫描线程已结束", flush=True)
        rows = window.report_panel.table.rowCount()
        counts_text = window.report_panel.summary_label.text()
        print(f"[3/3] 报告表格行数: {rows}", flush=True)
        print(f"      统计: {counts_text}", flush=True)
        if rows < 2:
            print("[!] 错误行数不足 2", flush=True)
            window.close()
            app.exit(4)
            return
        if window.progress_bar.isVisible():
            print("[!] 进度条未隐藏", flush=True)
            window.close()
            app.exit(5)
            return
        print("=" * 50, flush=True)
        print("端到端验证通过 ✅", flush=True)
        window.close()
        app.exit(0)

    QTimer.singleShot(0, step_import)
    QTimer.singleShot(200, step_wait_worker)
    code = app.exec()
    return code


if __name__ == "__main__":
    zip_arg = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "test_card.zip")
    raise SystemExit(run(zip_arg))