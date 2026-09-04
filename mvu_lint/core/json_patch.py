"""JSON Patch (<UpdateVariable>) parser and schema path matching.

Real MVU cards do *not* use ``<!-- mvu: -->`` comments.  The AI emits variable
updates as a ``<UpdateVariable>`` block carrying a ``<JSONPatch>`` array in
RFC 6902 JSON Patch format:

    <UpdateVariable>
    <analysis>...</analysis>
    <JSONPatch>
    [
      {"op":"replace","path":"/世界/当前时间","value":"..."},
      {"op":"add","path":"/角色档案/新角色","value":{...}}
    ]
    </JSONPatch>
    </UpdateVariable>

The ``path`` field is a JSON Pointer rooted at the variable tree's top-level
containers.  This module:

  * extracts ``<UpdateVariable>`` blocks,
  * parses ``<JSONPatch>`` arrays,
  * maps JSON Pointer paths onto the schema path tree (array indices and
    dynamic record keys both match the ``*`` wildcard used by the loader),
  * infers the JSON type of a patch ``value``.

Template / instruction blocks (``[mvu_update]变量输出格式``) carry placeholder
paths such as ``/${...}``, ``/<顶层根>/<既有字段路径>`` or ``<新键>``; those are
format specs for the AI, not concrete data, and are recognised and skipped.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


# RFC 6902 operations accepted by the MVU update pipeline.
VALID_OPS = {"add", "replace", "remove", "move"}

# <UpdateVariable> / <UpdateVariablevariable> (cards match both spellings).
_UPD_OPEN_RE = re.compile(
    r"<UpdateVariable(?:variable)?\s*>", re.IGNORECASE
)
_UPD_CLOSE_RE = re.compile(
    r"</UpdateVariable(?:variable)?\s*>", re.IGNORECASE
)

_JSONPATCH_RE = re.compile(
    r"<JSONPatch\s*>([\s\S]*?)</JSONPatch\s*>", re.IGNORECASE
)

# A path containing any of these is a format-spec placeholder, not a real path.
_TEMPLATE_MARKERS = ("${", "<顶层", "<既有", "<新键", "<正文", "<字段", "<分析")

# A malformed ``~`` escape: ~ must be followed by 0 or 1 (RFC 6901).
_BAD_ESCAPE_RE = re.compile(r"~(?![01])")


@dataclass
class JSONPatchOp:
    """One parsed JSON Patch operation."""
    op: str
    path: str
    value: Any = None
    from_: Optional[str] = None
    line: int = 0
    has_value: bool = False


@dataclass
class UpdateVariableBlock:
    """A matched ``<UpdateVariable> ... </UpdateVariable>`` region."""
    start: int
    end: int
    inner: str
    line: int


def extract_update_variable_blocks(
    content: str,
) -> Tuple[List[UpdateVariableBlock], List[Tuple[int, int]]]:
    """Find ``<UpdateVariable>`` blocks.

    Returns ``(blocks, unclosed)`` where ``unclosed`` is a list of
    ``(match_start, match_end)`` for opening tags without a matching close tag.
    """
    blocks: List[UpdateVariableBlock] = []
    unclosed: List[Tuple[int, int]] = []

    i = 0
    n = len(content)
    while i < n:
        open_m = _UPD_OPEN_RE.search(content, i)
        if open_m is None:
            break
        close_m = _UPD_CLOSE_RE.search(content, open_m.end())
        if close_m is None:
            unclosed.append((open_m.start(), open_m.end()))
            break
        blocks.append(UpdateVariableBlock(
            start=open_m.start(),
            end=close_m.end(),
            inner=content[open_m.end():close_m.start()],
            line=content[:open_m.start()].count("\n") + 1,
        ))
        i = close_m.end()

    return blocks, unclosed


def extract_json_patch_blocks(
    inner: str, base_line: int = 1
) -> Tuple[List[Tuple[str, int]], List[Tuple[int, int]]]:
    """Extract ``<JSONPatch>`` bodies (text, line) and unmatched open tags."""
    blocks: List[Tuple[str, int]] = []
    unclosed: List[Tuple[int, int]] = []

    for m in _JSONPATCH_RE.finditer(inner):
        line = base_line + inner[:m.start()].count("\n")
        blocks.append((m.group(1), line))

    # Detect <JSONPatch> with no matching close inside this block.
    pos = 0
    while True:
        o = re.search(r"<JSONPatch\s*>", inner[pos:], re.IGNORECASE)
        if o is None:
            break
        abs_start = pos + o.start()
        if not re.search(r"</JSONPatch\s*>", inner[abs_start:], re.IGNORECASE):
            unclosed.append((abs_start, abs_start + o.end() - o.start()))
        pos = abs_start + o.end() - o.start()

    return blocks, unclosed


def is_template_text(text: str) -> bool:
    """True if text is a format-spec template rather than concrete JSON."""
    return any(marker in text for marker in _TEMPLATE_MARKERS)


def parse_json_patch(json_text: str, line: int = 0) -> List[JSONPatchOp]:
    """Parse a JSON Patch array body into ops.

    Raises ValueError if the body is not a JSON array of objects.
    """
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("JSONPatch 内容必须是 JSON 数组")
    ops: List[JSONPatchOp] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("JSONPatch 数组的每一项必须是对象")
        op = item.get("op", "")
        path = item.get("path", "")
        value = item.get("value")
        from_ = item.get("from")
        ops.append(JSONPatchOp(
            op=op if isinstance(op, str) else "",
            path=path if isinstance(path, str) else "",
            value=value,
            from_=from_ if isinstance(from_, str) else None,
            line=line,
            has_value="value" in item,
        ))
    return ops


def json_pointer_to_segments(path: str) -> Optional[List[str]]:
    """Decode an RFC 6901 JSON Pointer into path segments.

    Returns None for a malformed pointer (must start with ``/`` or be empty;
    ``~`` must be followed by 0 or 1).
    """
    if path == "":
        return []
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    segments: List[str] = []
    for raw in path.split("/")[1:]:
        if raw == "":
            return None  # "//" → empty segment is invalid mid-pointer
        if "~" in raw:
            if _BAD_ESCAPE_RE.search(raw):
                return None
            raw = raw.replace("~1", "/").replace("~0", "~")
        segments.append(raw)
    return segments


def infer_json_type(value: Any) -> str:
    """Infer a schema-style type name from a decoded JSON value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "any"


# ── Schema path tree matching ──────────────────────────────────────

def _build_trie(paths: Set[str]) -> Dict[str, Any]:
    """Build a nested dict trie from dotted paths (``*`` is a wildcard node)."""
    root: Dict[str, Any] = {}
    for path in paths:
        node = root
        for seg in path.split("."):
            node = node.setdefault(seg, {})
        node["#leaf"] = True
    return root


def _match_segments(
    node: Dict[str, Any], segments: List[str], idx: int, matched: List[str]
) -> Optional[str]:
    """Recursively match pointer segments against the schema trie.

    Returns the matched dotted schema path (with ``*`` for wildcard nodes).
    """
    if idx == len(segments):
        return ".".join(matched) if "#leaf" in node else None
    seg = segments[idx]
    if seg in node:
        r = _match_segments(node[seg], segments, idx + 1, matched + [seg])
        if r:
            return r
    if "*" in node:
        r = _match_segments(node["*"], segments, idx + 1, matched + ["*"])
        if r:
            return r
    return None


def _node_exists(node: Dict[str, Any], segments: List[str]) -> bool:
    """True if the pointer (container or leaf) exists in the trie."""
    cur = node
    for seg in segments:
        if seg in cur:
            cur = cur[seg]
        elif "*" in cur:
            cur = cur["*"]
        else:
            return False
    return True


class SchemaPathMatcher:
    """Match JSON Pointer segments against a schema path set."""

    def __init__(self, schema_paths: Set[str]):
        self._paths = schema_paths
        self._trie = _build_trie(schema_paths)

    def match(self, segments: List[str]) -> Optional[str]:
        """Return the matched dotted schema path (leaf) or None."""
        return _match_segments(self._trie, segments, 0, [])

    def exists(self, segments: List[str]) -> bool:
        """True if the pointer names a schema node (container or leaf)."""
        return _node_exists(self._trie, segments)
