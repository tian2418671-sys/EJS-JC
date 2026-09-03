"""Project scanner — ZIP extraction + directory recognition + file_index."""
from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class FileEntry:
    """A single file in the scanned project."""
    file_path: str        # relative path
    file_type: str        # worldbook / script / interface / schema
    absolute_path: str


@dataclass
class ProjectInfo:
    """Scanned project information."""
    root_dir: str
    source: str           # zip path or directory path
    schema_path: Optional[str] = None    # absolute path to schema file
    schema_form: str = ""  # "json" or "ts" or ""
    files: List[FileEntry] = field(default_factory=list)

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


# Directory name → file type mapping
_DIR_TYPE_MAP = {
    "世界书": "worldbook",
    "worldbook": "worldbook",
    "脚本": "script",
    "script": "script",
    "scripts": "script",
    "界面": "interface",
    "interface": "interface",
    "ui": "interface",
}


class ProjectScanner:
    """Scan ZIP archives and directories for MVU project structure."""

    def scan_zip(self, zip_path: str, extract_dir: Optional[str] = None) -> ProjectInfo:
        """Extract ZIP and scan the resulting directory."""
        if extract_dir is None:
            extract_dir = tempfile.mkdtemp(prefix="mvu_lint_")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        return self.scan_directory(extract_dir, source=zip_path)

    def scan_directory(self, dir_path: str, source: str = "") -> ProjectInfo:
        """Scan a directory for project structure."""
        root = Path(dir_path)
        files: List[FileEntry] = []
        schema_path: Optional[str] = None
        schema_form: str = ""

        # Look for schema.json first, then schema.ts
        for pattern in ("schema.json", "**/schema.json"):
            matches = list(root.glob(pattern))
            if matches:
                schema_path = str(matches[0])
                schema_form = "json"
                break
        if not schema_path:
            for pattern in ("schema.ts", "**/schema.ts"):
                matches = list(root.glob(pattern))
                if matches:
                    schema_path = str(matches[0])
                    schema_form = "ts"
                    break

        # Scan all files
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            # Skip common non-project files
            if p.suffix.lower() in (".exe", ".dll", ".png", ".jpg", ".jpeg",
                                     ".gif", ".ico", ".zip"):
                continue

            rel_path = str(p.relative_to(root)).replace("\\", "/")
            file_type = self._classify_file(rel_path)
            if file_type:
                files.append(FileEntry(
                    file_path=rel_path,
                    file_type=file_type,
                    absolute_path=str(p),
                ))

        return ProjectInfo(
            root_dir=str(root),
            source=source,
            schema_path=schema_path,
            schema_form=schema_form,
            files=files,
        )

    def _classify_file(self, rel_path: str) -> Optional[str]:
        """Classify a file by its path and name.

        Returns one of: schema, worldbook, script, interface
        or None if the file should be skipped.
        """
        path = Path(rel_path)
        name = path.name.lower()
        parts = [p.lower() for p in path.parts]

        # Schema files
        if name in ("schema.json", "schema.ts"):
            return "schema"

        # Check directory-based classification
        for part in parts:
            if part in _DIR_TYPE_MAP:
                return _DIR_TYPE_MAP[part]

        # Extension-based classification for files not in known dirs
        if name.endswith((".ejs", ".html", ".htm")):
            return "interface"
        if name.endswith((".js", ".ts", ".mjs")):
            return "script"
        if name.endswith(".json"):
            # JSON files not in known dirs — treat as worldbook entries
            return "worldbook"
        if name.endswith((".txt", ".md")):
            return "worldbook"

        return None

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute MD5 hash of file content for incremental scanning."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()
