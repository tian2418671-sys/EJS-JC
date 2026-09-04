"""RAG knowledge-base service (Phase 5 / F7) — persistent VectorDB facade.

Thin, high-level wrapper over :class:`~mvu_lint.db.vector_db.VectorDB` that
owns the persistent on-disk knowledge base under
``%APPDATA%/MvuEjsLinter/knowledge.db`` and exposes the operations the
explanation engine needs (search / add chunk / count).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from ..db.vector_db import VectorDB


def default_knowledge_db_path() -> Path:
    """Return the persistent knowledge-base database path."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / ".local" / "share"
        )
    return Path(base) / "MvuEjsLinter" / "knowledge.db"


class RAGService:
    """Owns the knowledge base and its seed data."""

    def __init__(self, db_path: Optional[str] = None):
        path = db_path or str(default_knowledge_db_path())
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.vector_db = VectorDB(path)
        self.vector_db.init_default_knowledge()

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """Search knowledge chunks by similarity (with NumPy fallback)."""
        return self.vector_db.search(query, top_k=top_k)

    def add_chunk(self, content: str, source_type: str = "docs",
                  title: str = "", chunk_id: Optional[str] = None,
                  source_path: str = "") -> int:
        """Add a knowledge chunk and return its rowid."""
        return self.vector_db.add_chunk(
            content,
            source_type=source_type,
            title=title,
            chunk_id=chunk_id,
            source_path=source_path,
        )

    def chunk_count(self) -> int:
        """Return the number of knowledge chunks currently stored."""
        row = self.vector_db.conn.execute(
            "SELECT count(*) FROM knowledge_chunks"
        ).fetchone()
        return row[0]

    def close(self):
        self.vector_db.close()
