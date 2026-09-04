"""Project scanner — character card import + content-block file_index.

The correct import format is a NPC role card (角色卡):
  - PNG card: JSON embedded in the PNG ``tEXt chara`` chunk (base64)
  - JSON card: plain ``.json`` chara_card_v2 / legacy card

From the card we build a ``file_index`` of *content blocks* (worldbook
entries, first_mes, regex scripts, depth prompt…) instead of extracting
a ZIP archive to disk.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .card_loader import CharacterCard, load_card


@dataclass
class FileEntry:
    """A single content block in the scanned character card."""
    file_path: str        # logical path (e.g. 世界书/entry_003)
    file_type: str        # worldbook / script / interface / schema
    absolute_path: str    # source card path (for write-back)
    content: str = ""     # in-memory text content
    json_pointer: str = ""  # JSON pointer into the card dict


@dataclass
class ProjectInfo:
    """Scanned character card information."""
    root_dir: str
    source: str           # card path (.png / .json)
    schema_path: Optional[str] = None    # unused for cards; kept for compat
    schema_form: str = ""  # "json" / "ts" / ""
    files: List[FileEntry] = field(default_factory=list)
    card: Optional[CharacterCard] = None

    def to_dict(self) -> dict:
        return {
            "root_dir": self.root_dir,
            "source": self.source,
            "schema_path": self.schema_path,
            "schema_form": self.schema_form,
            "file_count": len(self.files),
            "files": [
                {"file_path": f.file_path, "file_type": f.file_type}
                for f in self.files
            ],
        }


class ProjectScanner:
    """Scan character cards (PNG/JSON) for MVU project structure."""

    def scan_card(self, card_path: str) -> ProjectInfo:
        """Parse a character card and index its content blocks."""
        card = load_card(card_path)
        root = Path(card_path).parent

        files: List[FileEntry] = []
        for block in card.blocks:
            files.append(FileEntry(
                file_path=block.file_path,
                file_type=block.file_type,
                absolute_path=str(Path(card_path).resolve()),
                content=block.content,
                json_pointer=block.json_pointer,
            ))

        return ProjectInfo(
            root_dir=str(root),
            source=str(Path(card_path).resolve()),
            files=files,
            card=card,
        )

    def scan_directory(self, dir_path: str, source: str = "") -> ProjectInfo:
        """Deprecated: legacy directory scan. Raises to guide users to cards."""
        raise NotImplementedError(
            "目录扫描已废弃 — 请导入角色卡文件（.png / .json）"
        )

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute MD5 hash of content for incremental scanning."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()
