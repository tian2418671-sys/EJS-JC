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
    round_number INTEGER,
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
    round_id INTEGER,
    stat_data TEXT,
    changed_paths TEXT,
    FOREIGN KEY (round_id) REFERENCES simulation_rounds(id)
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
