"""Application controller — orchestrates scan + checks + database.

GUI-agnostic on purpose: this module has no Qt imports, which keeps
it fully unit-testable without a display (see tests/test_app_controller.py).
The GUI layer wraps these calls in a QThread for responsiveness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..core.ejs_parser import EJSParser
from ..core.project_scanner import ProjectInfo, ProjectScanner
from ..core.schema_loader import SchemaLoader
from ..db.database import DatabaseManager
from ..models.check_result import CheckResult


@dataclass
class ScanSummary:
    """Result summary of one static-check run."""
    total_files: int = 0
    files_scanned: int = 0          # files that actually contained EJS
    errors_inserted: int = 0
    schema_form: str = ""           # "json" / "ts" / ""
    schema_path_count: int = 0
    degraded: bool = False          # MVU checks fell back to degraded mode
    degraded_reason: str = ""
    counts: dict = field(default_factory=dict)  # {"Lv.1": n, "Lv.2": n, ...}

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "files_scanned": self.files_scanned,
            "errors_inserted": self.errors_inserted,
            "schema_form": self.schema_form,
            "schema_path_count": self.schema_path_count,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "counts": self.counts,
        }


class AppController:
    """Orchestrates project import, static checks and the project DB."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager(":memory:")
        self.scanner = ProjectScanner()
        self.parser = EJSParser()
        self.project: Optional[ProjectInfo] = None
        self.schema_info = None
        self.schema_error: Optional[str] = None

    # ── Project import ────────────────────────────────────────────

    def import_zip(self, zip_path: str) -> ProjectInfo:
        """Extract a role-card ZIP, index its files, load its schema."""
        self.project = self.scanner.scan_zip(zip_path)
        for entry in self.project.files:
            self.db.insert_file_index(entry.file_path, entry.file_type)
        # A new project starts with a clean error table.
        self.db.clear_errors()
        self._load_schema()
        return self.project

    def _load_schema(self):
        """Load schema.json (or mark degraded mode)."""
        self.schema_info = None
        self.schema_error = None
        if not self.project:
            return
        if self.project.schema_form == "json" and self.project.schema_path:
            try:
                loader = SchemaLoader()
                self.schema_info = loader.load_from_json(self.project.schema_path)
            except Exception as exc:  # non-fatal; report degraded mode
                self.schema_error = str(exc)
        elif self.project.schema_form == "ts":
            self.schema_error = "schema.ts 仅支持文本降级扫描（Phase 2 启用）"
        else:
            self.schema_error = "未找到 schema.json，MVU 检查将降级为文本级扫描"

    def degraded_reason(self) -> str:
        """Human-readable reason when schema-driven checks are unavailable."""
        if self.schema_info is not None:
            return ""
        return self.schema_error or "未找到 schema.json"

    # ── Static check ──────────────────────────────────────────────

    def run_static_check(self,
                         progress_cb: Optional[Callable[[int, int], None]] = None
                         ) -> ScanSummary:
        """Run EJS static checks on all project files.

        progress_cb(done, total) is invoked after each file.
        """
        if not self.project:
            raise RuntimeError("尚未导入任何项目（先拖入角色卡 ZIP）")

        self.db.clear_errors()
        total = len(self.project.files)
        scanned = 0
        inserted = 0

        for index, entry in enumerate(self.project.files):
            if entry.file_type != "schema":
                try:
                    with open(entry.absolute_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except (UnicodeDecodeError, OSError):
                    content = None

                if content is not None and "<%" in content:
                    scanned += 1
                    result = self.parser.parse(content, entry.file_path)
                    for check in result.check_results:
                        stored_id = self.db.insert_check_result(check, prefix="EJS")
                        if stored_id:
                            inserted += 1

            if progress_cb:
                progress_cb(index + 1, total)

        schema_form = self.project.schema_form
        counts = self.db.get_error_counts()
        degraded = self.schema_info is None

        return ScanSummary(
            total_files=total,
            files_scanned=scanned,
            errors_inserted=inserted,
            schema_form=schema_form,
            schema_path_count=len(self.schema_info.paths) if self.schema_info else 0,
            degraded=degraded,
            degraded_reason=self.degraded_reason(),
            counts=counts,
        )

    # ── Report queries ────────────────────────────────────────────

    def get_errors(self, level: Optional[str] = None) -> List[dict]:
        return self.db.get_errors(level=level, status=None)

    def get_counts(self) -> dict:
        return self.db.get_error_counts()

    def clear_errors(self):
        self.db.clear_errors()

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self):
        self.db.close()