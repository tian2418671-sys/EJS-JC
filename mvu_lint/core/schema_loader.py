"""Schema loader — dual-form schema.json reader (Decision 2).

Supports two forms:
  1. Standard JSON Schema (has $schema or properties top-level key)
  2. Pure data shape (Zod direct output — actual values with inferred types)

Array elements use * placeholder: 主角.物品栏.*.名称
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class SchemaPath:
    """A single path entry in the schema tree."""
    path: str
    type: str           # string / number / boolean / object / array / null
    is_leaf: bool
    parent_path: Optional[str] = None


@dataclass
class SchemaInfo:
    """Parsed schema information."""
    paths: List[SchemaPath]
    source: str = ""
    form: str = ""      # "json_schema" or "data_shape"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "form": self.form,
            "path_count": len(self.paths),
            "paths": [
                {
                    "path": p.path,
                    "type": p.type,
                    "is_leaf": p.is_leaf,
                    "parent_path": p.parent_path,
                }
                for p in self.paths
            ],
        }

    def get_path_set(self) -> Set[str]:
        """Return a set of all paths."""
        return {p.path for p in self.paths}

    def get_leaf_paths(self) -> Set[str]:
        """Return a set of leaf-only paths."""
        return {p.path for p in self.paths if p.is_leaf}

    def get_path_types(self) -> dict:
        """Return a dict mapping path → type."""
        return {p.path: p.type for p in self.paths}


class SchemaLoader:
    """Load and parse schema.json in dual forms."""

    def load_from_json(self, json_path: str) -> SchemaInfo:
        """Load schema from a JSON file."""
        path = Path(json_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.load_from_dict(data, source=str(path))

    def load_from_dict(self, data: dict, source: str = "") -> SchemaInfo:
        """Load schema from a Python dict.

        Automatically detects form:
          - Contains $schema or properties → standard JSON Schema
          - Otherwise → pure data shape
        """
        if "$schema" in data or "properties" in data:
            paths = self._parse_json_schema(data)
            form = "json_schema"
        else:
            paths = self._parse_data_shape(data)
            form = "data_shape"
        return SchemaInfo(paths=paths, source=source, form=form)

    # ── Standard JSON Schema ────────────────────────────────────────

    def _parse_json_schema(
        self, schema: dict, prefix: str = ""
    ) -> List[SchemaPath]:
        """Parse standard JSON Schema format recursively."""
        paths: List[SchemaPath] = []
        props = schema.get("properties", {})

        for key, val in props.items():
            path = f"{prefix}.{key}" if prefix else key
            node_type = val.get("type", "any")
            is_leaf = node_type not in ("object", "array")

            paths.append(SchemaPath(
                path=path,
                type=node_type,
                is_leaf=is_leaf,
                parent_path=prefix or None,
            ))

            if node_type == "object":
                paths.extend(self._parse_json_schema(val, path))
            elif node_type == "array":
                items = val.get("items", {})
                if isinstance(items, dict):
                    paths.extend(self._parse_json_schema(items, f"{path}.*"))

        return paths

    # ── Pure data shape ─────────────────────────────────────────────

    def _parse_data_shape(
        self, data: dict, prefix: str = ""
    ) -> List[SchemaPath]:
        """Parse pure data shape (Zod direct output) recursively."""
        paths: List[SchemaPath] = []

        for key, val in data.items():
            path = f"{prefix}.{key}" if prefix else key

            # Determine type from value (bool before int!)
            if isinstance(val, bool):
                node_type, is_leaf = "boolean", True
            elif isinstance(val, (int, float)):
                node_type, is_leaf = "number", True
            elif isinstance(val, str):
                node_type, is_leaf = "string", True
            elif isinstance(val, list):
                node_type, is_leaf = "array", False
            elif isinstance(val, dict):
                node_type, is_leaf = "object", False
            elif val is None:
                node_type, is_leaf = "null", True
            else:
                node_type, is_leaf = "any", True

            paths.append(SchemaPath(
                path=path,
                type=node_type,
                is_leaf=is_leaf,
                parent_path=prefix or None,
            ))

            # Recurse into containers
            if node_type == "object":
                paths.extend(self._parse_data_shape(val, path))
            elif node_type == "array" and val:
                # Recurse into first element if it's a dict
                if isinstance(val[0], dict):
                    paths.extend(self._parse_data_shape(val[0], f"{path}.*"))

        return paths
