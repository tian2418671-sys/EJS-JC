"""Application controller — orchestrates card import + checks + database.

GUI-agnostic on purpose: this module has no Qt imports, which keeps
it fully unit-testable without a display (see tests/test_app_controller.py).
The GUI layer wraps these calls in a QThread for responsiveness.

Import format: NPC role cards (PNG with embedded chara JSON, or plain JSON).
ZIP archives are NOT a valid import format for this tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..core.card_loader import (
    extract_schema_dict,
    load_card,
    write_card,
)
from ..core.ejs_parser import EJSParser
from ..core.project_scanner import ProjectInfo, ProjectScanner
from ..core.schema_loader import SchemaLoader
from ..core.static_checker import StaticChecker
from ..core.auto_fixer import AutoFixer
from ..db.database import DatabaseManager
from ..models.check_result import CheckResult


@dataclass
class ScanSummary:
    """Result summary of one static-check run."""
    total_files: int = 0
    files_scanned: int = 0          # blocks that actually contained EJS
    errors_inserted: int = 0
    schema_form: str = ""           # "json" / "ts" / "data_shape" / ""
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
    """Orchestrates character-card import, static checks and the project DB."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager(":memory:")
        self.scanner = ProjectScanner()
        self.parser = EJSParser()
        self.checker = StaticChecker()
        self.project: Optional[ProjectInfo] = None
        self.schema_info = None
        self.schema_error: Optional[str] = None

    # ── Project import ────────────────────────────────────────────

    def import_card(self, card_path: str) -> ProjectInfo:
        """Import a PNG/JSON role card, index its content blocks, load schema.

        Raises ValueError for unsupported formats (e.g. .zip files).
        """
        card = load_card(card_path)  # validates format up front
        self.project = self.scanner.scan_card(card_path)
        for entry in self.project.files:
            self.db.insert_file_index(
                entry.file_path, entry.file_type,
                content_hash=self.scanner.compute_hash(entry.content),
            )
        # A new project starts with a clean error table.
        self.db.clear_errors()
        self._load_schema()
        return self.project

    def import_zip(self, zip_path: str) -> ProjectInfo:
        """Legacy ZIP import — rejected. Cards must be PNG or JSON."""
        raise ValueError(
            "ZIP 不是有效的导入格式 — 请导入角色卡文件（.png 或 .json）"
        )

    def _load_schema(self):
        """Load schema from the card's embedded variable initial values."""
        self.schema_info = None
        self.schema_error = None
        if not self.project or self.project.card is None:
            return
        try:
            data = extract_schema_dict(self.project.card)
            if data:
                loader = SchemaLoader()
                self.schema_info = loader.load_from_dict(
                    data, source=self.project.source
                )
            else:
                self.schema_error = "角色卡中未找到「# 变量初始值」块，MVU 检查将降级为文本级扫描"
        except Exception as exc:  # non-fatal; report degraded mode
            self.schema_error = f"变量初始值解析失败: {exc}"

    def degraded_reason(self) -> str:
        """Human-readable reason when schema-driven checks are unavailable."""
        if self.schema_info is not None:
            return ""
        return self.schema_error or "未找到变量初始值定义"

    # ── Static check ──────────────────────────────────────────────

    def run_static_check(
        self,
        progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> ScanSummary:
        """Run full static checks: EJS + MVU commands + linkage + initvar.

        progress_cb(done, total) is invoked after each content block.
        """
        if not self.project:
            raise RuntimeError("尚未导入任何项目（先导入 PNG/JSON 角色卡）")

        self.db.clear_errors()
        total = len(self.project.files)
        scanned = 0
        inserted = 0

        for index, entry in enumerate(self.project.files):
            if entry.file_type != "schema":
                content = entry.content

                if content is not None:
                    has_ejs = "<%" in content
                    has_mvu = "<!--" in content and "mvu" in content.lower()
                    has_initvar = "initvar" in content

                    if has_ejs or has_mvu or has_initvar:
                        scanned += 1

                    # 1. EJS tag + dangerous output checks
                    result = None
                    if has_ejs:
                        result = self.parser.parse(content, entry.file_path)
                        for check in result.check_results:
                            stored_id = self.db.insert_check_result(check, prefix="EJS")
                            if stored_id:
                                inserted += 1

                    # 2. MVU command format + path validation
                    if has_mvu:
                        mvu_results = self.checker.check_mvu_commands(
                            content, entry.file_path, self.schema_info
                        )
                        for check in mvu_results:
                            stored_id = self.db.insert_check_result(check, prefix="MVU")
                            if stored_id:
                                inserted += 1

                    # 3. EJS ↔ Schema linkage check
                    if has_ejs and self.schema_info is not None and result is not None:
                        link_results = self.checker.check_linkage(
                            result.variable_refs, entry.file_path,
                            self.schema_info
                        )
                        for check in link_results:
                            stored_id = self.db.insert_check_result(check, prefix="LINK")
                            if stored_id:
                                inserted += 1

                    # 4. initvar completeness + type consistency
                    if has_initvar and self.schema_info is not None:
                        initvar_results = self.checker.check_initvar(
                            content, entry.file_path, self.schema_info
                        )
                        for check in initvar_results:
                            stored_id = self.db.insert_check_result(check, prefix="MVU")
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

    def set_error_status(self, error_id: str, status: str) -> bool:
        """Update one error's status and return whether it matched a row."""
        return self.db.set_error_status(error_id, status)

    # ── Auto-fix ────────────────────────────────────────────────────

    def _find_file_entry(self, file_path: str):
        """Find a FileEntry by its logical path."""
        if not self.project:
            return None
        for entry in self.project.files:
            if entry.file_path == file_path:
                return entry
        return None

    def _read_file_content(self, file_path: str) -> Optional[str]:
        """Return content of a project block by logical path."""
        entry = self._find_file_entry(file_path)
        if not entry:
            return None
        return entry.content

    def generate_fix_preview(self, error: dict) -> Optional[str]:
        """Generate a fix preview for an auto-fixable error.

        Args:
            error: Error dict from DB (must contain file_path, auto_fixable, etc.)

        Returns:
            Preview text, or None if not fixable / file not found.
        """
        if not error.get("auto_fixable"):
            return None
        content = self._read_file_content(error.get("file_path", ""))
        if content is None:
            return None
        fixer = AutoFixer(self.schema_info)
        return fixer.generate_preview(error, content)

    def apply_auto_fix(self, error: dict) -> Optional[str]:
        """Apply an auto-fix and write the corrected block back to the card.

        The fixed block is written back into the character card JSON
        (JSON cards are rewritten directly; PNG cards get a re-encoded
        ``chara`` tEXt chunk).

        Args:
            error: Error dict from DB.

        Returns:
            The fixed content string on success, or None on failure.
        """
        if not error.get("auto_fixable"):
            return None
        file_path = error.get("file_path", "")
        entry = self._find_file_entry(file_path)
        if not entry:
            return None
        content = self._read_file_content(file_path)
        if content is None:
            return None
        fixer = AutoFixer(self.schema_info)
        fixed = fixer.apply_fix(error, content)
        if fixed is None:
            return None

        # Write the fixed text back into the card dict at the block's pointer
        try:
            card = load_card(entry.absolute_path)
            node = card.data
            parts = _pointer_parts(entry.json_pointer)
            if not parts or not parts[0] == "data":
                return None
            for part in parts[1:-1]:
                if isinstance(part, int):
                    node = node[part]
                else:
                    node = node.get(part, {})
            last = parts[-1]
            if isinstance(last, int):
                node[last] = fixed
            else:
                node[last] = fixed
            write_card(entry.absolute_path, _card_dict(card))
        except Exception:
            return None

        # Update in-memory content + mark error as fixed in DB
        entry.content = fixed
        self.db.set_error_status(error.get("error_id", ""), "fixed")
        return fixed

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self):
        self.db.close()


def _pointer_parts(pointer: str) -> List[object]:
    """Split a JSON pointer into path parts (str keys / int indexes)."""
    if not pointer or not pointer.startswith("/"):
        return []
    parts: List[object] = []
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token)
    return parts


def _card_dict(card) -> dict:
    """Reconstruct the top-level card dict from a CharacterCard."""
    if card.spec and card.spec != "legacy":
        return {"spec": card.spec, "spec_version": card.spec_version, "data": card.data}
    return card.data
