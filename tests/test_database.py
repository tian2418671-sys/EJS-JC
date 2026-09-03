"""Database layer tests — schema (v2.1), global error_id allocation."""
from __future__ import annotations

import pytest

from mvu_lint.db.database import DatabaseManager
from mvu_lint.models.check_result import (
    CheckResult,
    ErrorCategory,
    ErrorLevel,
)


@pytest.fixture
def db():
    manager = DatabaseManager(":memory:")
    yield manager
    manager.close()


def _mk_result(error_id: str, level=ErrorLevel.LV2, is_static=False,
               file_path="世界书/a.yaml") -> CheckResult:
    return CheckResult(
        error_id=error_id,
        level=level,
        category=ErrorCategory.EJS,
        file_path=file_path,
        line_number=3,
        path="主角.好感度" if is_static else None,
        message="测试错误",
        suggestion="修复",
        is_static=is_static,
    )


def test_static_errors_has_is_static_column(db):
    """v2.1 schema: is_static column must exist."""
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(static_errors)")}
    assert "is_static" in cols


def test_insert_persists_is_static(db):
    db.insert_check_result(_mk_result("EJS-0001", is_static=True))
    rows = db.get_all_errors()
    assert rows[0]["is_static"] == 1


def test_duplicate_error_id_gets_fresh_global_id(db):
    """Parser counters restart per file → collisions must be resolved."""
    db.insert_check_result(_mk_result("EJS-0001"))
    stored = db.insert_check_result(_mk_result("EJS-0001"))
    rows = db.get_all_errors()
    assert len(rows) == 2
    ids = {r["error_id"] for r in rows}
    assert stored in ids          # fresh id was stored
    assert stored != "EJS-0001"   # not the colliding one
    assert stored == "EJS-0002"


def test_next_error_id_monotonic_after_clear(db):
    """Clearing rows must not reuse old ids."""
    db.insert_check_result(_mk_result("EJS-0001"))
    db.insert_check_result(_mk_result("EJS-0002"))
    db.clear_errors()
    assert db.next_error_id("EJS") == "EJS-0003"


def test_next_error_id_cross_prefix_shared_watermark(db):
    """All prefixes share one monotonically rising id line.

    This guarantees absolute uniqueness of error_id (the table-level
    UNIQUE constraint) under any mix of prefixes / deletes / clears.
    """
    assert db.next_error_id("MVU") == "MVU-0001"  # empty table
    db.insert_check_result(_mk_result("EJS-0001"))
    assert db.next_error_id("MVU") == "MVU-0002"  # watermark advanced
    assert db.next_error_id("EJS") == "EJS-0002"


def test_get_errors_filter_by_level(db):
    db.insert_check_result(_mk_result("EJS-0001", level=ErrorLevel.LV1))
    db.insert_check_result(_mk_result("EJS-0002", level=ErrorLevel.LV2))
    db.insert_check_result(_mk_result("EJS-0003", level=ErrorLevel.LV2))
    lv2 = db.get_errors(level="Lv.2")
    assert len(lv2) == 2
    assert all(e["level"] == "Lv.2" for e in lv2)


def test_get_error_counts(db):
    db.insert_check_result(_mk_result("EJS-0001", level=ErrorLevel.LV1))
    db.insert_check_result(_mk_result("EJS-0002", level=ErrorLevel.LV3))
    db.insert_check_result(_mk_result("EJS-0003", level=ErrorLevel.LV3))
    counts = db.get_error_counts()
    assert counts == {"Lv.1": 1, "Lv.2": 0, "Lv.3": 2, "Lv.4": 0}


def test_clear_errors_empties_table(db):
    db.insert_check_result(_mk_result("EJS-0001"))
    db.clear_errors()
    assert db.get_all_errors() == []