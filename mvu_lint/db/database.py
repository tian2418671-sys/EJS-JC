"""Database manager — SQLite connection and table initialization.

Manages the project database (in-memory or temp file) with tables:
  static_errors, simulation_rounds, state_snapshots, schema_cache, file_index
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from ..models.check_result import CheckResult


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS static_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id TEXT UNIQUE,
    level TEXT,
    category TEXT,
    file_path TEXT,
    line_number INTEGER,
    path TEXT,
    message TEXT,
    suggestion TEXT,
    auto_fixable INTEGER DEFAULT 0,
    fix_preview TEXT,
    ai_explanation TEXT,
    status TEXT DEFAULT 'pending',
    is_static INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS simulation_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number INTEGER NOT NULL,
    user_input TEXT,
    ai_raw_output TEXT,
    parsed_commands TEXT,
    ejs_rendered TEXT,
    errors TEXT,
    warnings TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS state_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    stat_data TEXT,
    changed_paths TEXT,
    FOREIGN KEY (round_id) REFERENCES simulation_rounds(id)
);

CREATE TABLE IF NOT EXISTS simulation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    file_path TEXT,
    command_type TEXT,
    path TEXT,
    op TEXT,
    value TEXT,
    before_value TEXT,
    after_value TEXT,
    status TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (round_id) REFERENCES simulation_rounds(id)
);

CREATE TABLE IF NOT EXISTS dynamic_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT UNIQUE,
    level TEXT,
    category TEXT DEFAULT '动态',
    file_path TEXT,
    line_number INTEGER,
    round_number INTEGER,
    path TEXT,
    message TEXT,
    suggestion TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    is_static INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schema_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE,
    type TEXT,
    is_leaf INTEGER,
    parent_path TEXT,
    source TEXT DEFAULT 'json_schema'
);

CREATE TABLE IF NOT EXISTS file_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE,
    file_type TEXT,
    content_hash TEXT,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
class DatabaseManager:
    """Manage SQLite database connections and provide query interface."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        # SQLite is compiled in serialized mode: a single connection may be
        # used from multiple threads. Disable the python-side guard because
        # scans write from a QThread while the GUI reads after completion
        # (signal ordering guarantees no concurrent access).
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    # ── file_index ──────────────────────────────────────────────────

    def insert_file_index(self, file_path: str, file_type: str,
                          content_hash: Optional[str] = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO file_index (file_path, file_type, content_hash) "
            "VALUES (?, ?, ?)",
            (file_path, file_type, content_hash),
        )
        self.conn.commit()

    def get_file_index(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM file_index").fetchall()
        return [dict(r) for r in rows]

    # ── static_errors ───────────────────────────────────────────────

    def next_error_id(self, prefix: str = "EJS") -> str:
        """Allocate a globally-unique error_id (e.g. EJS-0007).

        Combines the highest numeric suffix currently in the table with
        sqlite_sequence (the AUTOINCREMENT watermark), so ids never go
        backwards even after rows are deleted or the table is cleared.
        """
        row = self.conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(error_id, ?) AS INTEGER)), 0) "
            "FROM static_errors WHERE error_id LIKE ?",
            (len(prefix) + 2, prefix + "-%"),
        ).fetchone()
        suffix_max = row[0]
        seq_row = self.conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'static_errors'"
        ).fetchone()
        seq_max = seq_row[0] if seq_row else 0
        return f"{prefix}-{max(suffix_max, seq_max) + 1:04d}"

    def insert_check_result(self, result: CheckResult,
                            prefix: str = "EJS") -> str:
        """Insert a check result; returns the stored error_id.

        If the incoming error_id collides with an existing row (e.g.
        parser-internal counters restart per file), a fresh globally
        unique id is allocated instead.
        """
        error_id = result.error_id or self.next_error_id(prefix)
        while True:
            try:
                self.conn.execute(
                    "INSERT INTO static_errors "
                    "(error_id, level, category, file_path, line_number, path, "
                    " message, suggestion, auto_fixable, fix_preview, status, is_static) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        error_id,
                        result.level.value,
                        result.category.value,
                        result.file_path,
                        result.line_number,
                        result.path,
                        result.message,
                        result.suggestion,
                        int(result.auto_fixable),
                        result.fix_preview,
                        result.status,
                        int(result.is_static),
                    ),
                )
                self.conn.commit()
                return error_id
            except sqlite3.IntegrityError:
                error_id = self.next_error_id(prefix)

    def get_all_errors(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM static_errors").fetchall()
        return [dict(r) for r in rows]

    def get_errors(self, level: Optional[str] = None,
                   status: Optional[str] = None) -> List[dict]:
        """Query errors with optional level / status filters."""
        sql = "SELECT * FROM static_errors WHERE 1=1"
        params: list = []
        if level:
            sql += " AND level = ?"
            params.append(level)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_error_counts(self) -> dict:
        """Return per-level counts: {"Lv.1": n, "Lv.2": n, ...}."""
        counts = {"Lv.1": 0, "Lv.2": 0, "Lv.3": 0, "Lv.4": 0}
        for row in self.conn.execute(
            "SELECT level, count(*) FROM static_errors GROUP BY level"
        ).fetchall():
            counts[row[0]] = row[1]
        return counts

    def clear_errors(self):
        """Remove all rows from static_errors (project re-scan)."""
        self.conn.execute("DELETE FROM static_errors")
        self.conn.commit()

    def has_blocking_errors(self) -> bool:
        """Check if any Lv.1/Lv.2/Lv.3 errors exist."""
        row = self.conn.execute(
            "SELECT count(*) FROM static_errors WHERE level IN ('Lv.1', 'Lv.2', 'Lv.3') "
            "AND status = 'pending'"
        ).fetchone()
        return row[0] > 0

    def set_error_status(self, error_id: str, status: str) -> bool:
        """Update a single error's status (pending / fixed / ignored).

        Returns True if exactly one row was affected.
        """
        cur = self.conn.execute(
            "UPDATE static_errors SET status = ? WHERE error_id = ?",
            (status, error_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_error(self, error_id: str) -> Optional[dict]:
        """Return a single error row by error_id, or None if not found."""
        row = self.conn.execute(
            "SELECT * FROM static_errors WHERE error_id = ?", (error_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_error_explanation(self, error_id: str, explanation: str) -> bool:
        """Persist an AI/template explanation onto an error row.

        Returns True if exactly one row was affected.
        """
        cur = self.conn.execute(
            "UPDATE static_errors SET ai_explanation = ? WHERE error_id = ?",
            (explanation, error_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── simulation rounds / snapshots / logs ────────────────────────

    def insert_simulation_round(
        self,
        round_number: int,
        user_input: str = "",
        ai_raw_output: str = "",
        parsed_commands: Optional[str] = None,
        ejs_rendered: str = "",
        errors: Optional[str] = None,
        warnings: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO simulation_rounds "
            "(round_number, user_input, ai_raw_output, parsed_commands, "
            " ejs_rendered, errors, warnings) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                round_number,
                user_input,
                ai_raw_output,
                parsed_commands,
                ejs_rendered,
                errors,
                warnings,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_state_snapshot(
        self,
        round_id: int,
        stat_data: str,
        changed_paths: str,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO state_snapshots (round_id, stat_data, changed_paths) "
            "VALUES (?, ?, ?)",
            (round_id, stat_data, changed_paths),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_simulation_log(self, round_id: int, file_path: str,
                              command_type: str, path: str, op: str,
                              value: str, before_value: str, after_value: str,
                              status: str, error: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO simulation_logs "
            "(round_id, file_path, command_type, path, op, value, "
            " before_value, after_value, status, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (round_id, file_path, command_type, path, op, value,
             before_value, after_value, status, error),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_simulation_rounds(self) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM simulation_rounds ORDER BY round_number"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_state_snapshots(self, round_id: Optional[int] = None) -> List[dict]:
        sql = "SELECT * FROM state_snapshots"
        params: list = []
        if round_id is not None:
            sql += " WHERE round_id = ?"
            params.append(round_id)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_simulation_logs(self, round_id: Optional[int] = None) -> List[dict]:
        sql = "SELECT * FROM simulation_logs"
        params: list = []
        if round_id is not None:
            sql += " WHERE round_id = ?"
            params.append(round_id)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def clear_simulation(self):
        """Remove all simulation data (rounds, snapshots, logs)."""
        self.conn.execute("DELETE FROM simulation_logs")
        self.conn.execute("DELETE FROM state_snapshots")
        self.conn.execute("DELETE FROM simulation_rounds")
        self.conn.commit()

    # ── dynamic findings (Phase 4 / F6) ─────────────────────────────

    def insert_dynamic_finding(self, finding: dict) -> str:
        """Insert one dynamic-locator finding; returns its finding_id."""
        finding_id = finding.get("error_id") or self.next_error_id("DYN")
        while True:
            try:
                self.conn.execute(
                    "INSERT INTO dynamic_findings "
                    "(finding_id, level, category, file_path, line_number, "
                    " round_number, path, message, suggestion, evidence, "
                    " status, is_static) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        finding_id,
                        finding.get("level", "Lv.3"),
                        finding.get("category", "动态"),
                        finding.get("file_path", ""),
                        finding.get("line_number"),
                        finding.get("round_number"),
                        finding.get("path"),
                        finding.get("message", ""),
                        finding.get("suggestion"),
                        finding.get("evidence", ""),
                        finding.get("status", "pending"),
                        int(finding.get("is_static", 0)),
                    ),
                )
                self.conn.commit()
                return finding_id
            except sqlite3.IntegrityError:
                finding_id = self.next_error_id("DYN")

    def get_dynamic_findings(self, level: Optional[str] = None) -> List[dict]:
        sql = ("SELECT finding_id AS error_id, level, category, file_path, "
               "line_number, round_number, path, message, suggestion, "
               "evidence, status, is_static "
               "FROM dynamic_findings WHERE 1=1")
        params: list = []
        if level:
            sql += " AND level = ?"
            params.append(level)
        sql += " ORDER BY COALESCE(round_number, 0), id"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def clear_dynamic_findings(self):
        self.conn.execute("DELETE FROM dynamic_findings")
        self.conn.commit()

    def set_dynamic_status(self, finding_id: str, status: str) -> bool:
        cur = self.conn.execute(
            "UPDATE dynamic_findings SET status = ? WHERE finding_id = ?",
            (status, finding_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── schema_cache ────────────────────────────────────────────────

    def insert_schema_path(self, path: str, path_type: str,
                           is_leaf: bool, parent_path: Optional[str] = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_cache (path, type, is_leaf, parent_path) "
            "VALUES (?, ?, ?, ?)",
            (path, path_type, int(is_leaf), parent_path),
        )
        self.conn.commit()

    def get_schema_paths(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM schema_cache").fetchall()
        return [dict(r) for r in rows]

    # ── lifecycle ───────────────────────────────────────────────────

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
