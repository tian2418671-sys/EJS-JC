"""Vector database — sqlite-vec wrapper with NumPy fallback (Decision 4).

Tries sqlite-vec extension first; falls back to NumPy brute-force
cosine similarity if the extension is unavailable.

Embeddings in Phase 0 use a deterministic hash-based bag-of-words
approach (not semantic).  Real semantic embeddings arrive in Phase 5
with the LLM module.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import List, Optional

import numpy as np

from ..knowledge.seed_data import get_default_chunks, get_default_error_patterns

_EMBEDDING_DIM = 384


def _simple_embedding(text: str, dim: int = _EMBEDDING_DIM) -> np.ndarray:
    """Generate a deterministic bag-of-words embedding via MD5 hashing."""
    vec = np.zeros(dim, dtype=np.float32)
    for word in text.replace("\n", " ").split():
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % dim
        vec[h] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class VectorDB:
    """Knowledge base vector store with automatic fallback."""

    def __init__(self, db_path: str = ":memory:"):
        self._use_vec: bool = False
        self._fallback_vectors: dict[int, np.ndarray] = {}  # rowid → vector
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # Try loading sqlite-vec
        self._try_load_vec()

        # Initialize tables
        self._init_tables()

    def _try_load_vec(self):
        """Attempt to load sqlite-vec extension; fall back to NumPy."""
        # Approach 1: sqlite_vec Python package
        try:
            import sqlite_vec
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            # Verify it works
            self.conn.execute("SELECT vec_version()").fetchone()
            self._use_vec = True
            return
        except Exception:
            pass

        # Approach 2: manual load_extension
        try:
            self.conn.enable_load_extension(True)
            self.conn.load_extension("vec0")
            self._use_vec = True
            return
        except Exception:
            pass

        # Fallback: NumPy brute-force
        self._use_vec = False

    def _init_tables(self):
        # Knowledge chunks (text metadata)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT UNIQUE,
                source_type TEXT,
                source_path TEXT,
                title TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS error_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT UNIQUE,
                error_level TEXT,
                regex_pattern TEXT,
                description TEXT,
                fix_suggestion TEXT,
                priority INTEGER DEFAULT 0
            );
        """)

        # Vector table (sqlite-vec only)
        if self._use_vec:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_vec "
                "USING vec0(embedding float[%d])" % _EMBEDDING_DIM
            )
        self.conn.commit()

    @property
    def use_vec_extension(self) -> bool:
        return self._use_vec

    # ── Knowledge chunks ────────────────────────────────────────────

    def add_chunk(self, content: str, source_type: str = "docs",
                  title: str = "", chunk_id: Optional[str] = None,
                  source_path: str = "") -> int:
        """Add a knowledge chunk and return its rowid."""
        if chunk_id is None:
            row = self.conn.execute(
                "SELECT count(*) FROM knowledge_chunks"
            ).fetchone()
            chunk_id = f"KB-{row[0] + 1:04d}"

        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO knowledge_chunks "
            "(chunk_id, source_type, source_path, title, content) "
            "VALUES (?, ?, ?, ?, ?)",
            (chunk_id, source_type, source_path, title, content),
        )
        self.conn.commit()
        rowid = cursor.lastrowid

        # Store embedding
        if rowid:
            vec = _simple_embedding(content)
            if self._use_vec:
                self.conn.execute(
                    "INSERT OR REPLACE INTO knowledge_chunks_vec (rowid, embedding) "
                    "VALUES (?, ?)",
                    (rowid, vec.tobytes()),
                )
                self.conn.commit()
            else:
                self._fallback_vectors[rowid] = vec

        return rowid

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """Search knowledge chunks by semantic similarity."""
        query_vec = _simple_embedding(query)

        if self._use_vec:
            # sqlite-vec requires LIMIT/k directly on the vec0 table;
            # use a subquery so the KNN constraint is recognized.
            rows = self.conn.execute(
                "SELECT c.id, c.chunk_id, c.title, c.content, c.source_type, "
                "       v.distance "
                "FROM ("
                "    SELECT rowid, distance "
                "    FROM knowledge_chunks_vec "
                "    WHERE embedding MATCH ? "
                "    LIMIT ?"
                ") v "
                "JOIN knowledge_chunks c ON c.id = v.rowid "
                "ORDER BY v.distance",
                (query_vec.tobytes(), top_k),
            ).fetchall()
        else:
            # NumPy brute-force cosine similarity
            if not self._fallback_vectors:
                return []
            sims = []
            for rowid, vec in self._fallback_vectors.items():
                sim = float(np.dot(query_vec, vec))
                sims.append((rowid, sim))
            sims.sort(key=lambda x: -x[1])
            top_ids = [r[0] for r in sims[:top_k]]
            if not top_ids:
                return []
            placeholders = ",".join("?" * len(top_ids))
            rows = self.conn.execute(
                f"SELECT id, chunk_id, title, content, source_type, NULL as distance "
                f"FROM knowledge_chunks WHERE id IN ({placeholders})",
                top_ids,
            ).fetchall()
            # Sort by similarity (already sorted, but SQL may reorder)
            id_to_sim = dict(sims)
            rows = sorted(rows, key=lambda r: -id_to_sim.get(r["id"], 0))

        return [dict(r) for r in rows]

    # ── Error patterns ──────────────────────────────────────────────

    def add_error_pattern(self, pattern_name: str, error_level: str,
                          regex_pattern: str, description: str = "",
                          fix_suggestion: str = "", priority: int = 0):
        self.conn.execute(
            "INSERT OR REPLACE INTO error_patterns "
            "(pattern_name, error_level, regex_pattern, description, "
            " fix_suggestion, priority) VALUES (?, ?, ?, ?, ?, ?)",
            (pattern_name, error_level, regex_pattern, description,
             fix_suggestion, priority),
        )
        self.conn.commit()

    def get_error_patterns(self) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM error_patterns ORDER BY priority DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Initialization ──────────────────────────────────────────────

    def init_default_knowledge(self):
        """Seed the knowledge base with default data (idempotent)."""
        # Skip if already initialized
        count = self.conn.execute(
            "SELECT count(*) FROM knowledge_chunks"
        ).fetchone()[0]
        if count > 0:
            return

        for chunk in get_default_chunks():
            self.add_chunk(
                content=chunk["content"],
                source_type=chunk.get("source_type", "docs"),
                title=chunk.get("title", ""),
                chunk_id=chunk.get("chunk_id"),
            )

        for pattern in get_default_error_patterns():
            self.add_error_pattern(
                pattern_name=pattern["pattern_name"],
                error_level=pattern["error_level"],
                regex_pattern=pattern["regex_pattern"],
                description=pattern.get("description", ""),
                fix_suggestion=pattern.get("fix_suggestion", ""),
                priority=pattern.get("priority", 0),
            )

    # ── Lifecycle ───────────────────────────────────────────────────

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
