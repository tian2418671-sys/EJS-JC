"""Character card loader — parse NPC role cards (PNG tEXt / JSON, chara_card_v2).

SillyTavern-style character cards are the real import format for this tool:
  - PNG card: JSON is base64-encoded inside the PNG ``tEXt`` chunk with keyword ``chara``
  - JSON card: a plain ``.json`` file with the same structure (chara_card_v2 or legacy)

From a parsed card we extract *content blocks* — every text area that can
contain EJS / MVU content:

  - ``data.character_book.entries[].content``  (worldbook entries)
  - ``data.first_mes`` / ``description`` / ``system_prompt`` / … (card text fields)
  - ``data.extensions.regex_scripts[].findRegex|replaceString``
  - ``data.extensions.depth_prompt.prompt``
  - ``data.extensions.tavern_helper.scripts[]``

The card also often embeds an initial-variable block ("# 变量初始值"), a
YAML-ish data shape that we parse into a schema dict for linkage checks.
"""
from __future__ import annotations

import base64
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ContentBlock:
    """One text block extracted from a character card (a checkable unit)."""
    file_path: str          # logical path shown in reports (e.g. 世界书/entry_003)
    file_type: str          # worldbook / script / interface / card_text
    content: str            # text to check (may be empty)
    json_pointer: str       # JSON pointer into card dict (e.g. /data/character_book/entries/0/content)


@dataclass
class CharacterCard:
    """Parsed NPC character card (chara_card_v2 or legacy)."""
    name: str
    spec: str
    spec_version: str
    data: dict
    source_path: str
    blocks: List[ContentBlock] = field(default_factory=list)
    is_png: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "spec": self.spec,
            "spec_version": self.spec_version,
            "source": self.source_path,
            "format": "png" if self.is_png else "json",
            "block_count": len(self.blocks),
            "blocks": [
                {
                    "file_path": b.file_path,
                    "file_type": b.file_type,
                    "content_len": len(b.content),
                    "json_pointer": b.json_pointer,
                }
                for b in self.blocks
            ],
        }


# ── Public API ───────────────────────────────────────────────────────


def load_card(path: str) -> CharacterCard:
    """Load a PNG or JSON character card and extract its content blocks.

    Raises:
        ValueError: if the file is not a readable character card.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"角色卡文件不存在: {path}")

    if p.suffix.lower() == ".png":
        card_json = _extract_png_chara(p)
        is_png = True
    elif p.suffix.lower() in (".json", ".jsonc"):
        try:
            card_json = json.loads(p.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"JSON 角色卡解析失败: {exc}") from exc
        is_png = False
    else:
        raise ValueError(
            f"不支持的导入格式: {p.suffix or '(无扩展名)'}（仅支持 .png / .json 角色卡）"
        )

    return _parse_card(card_json, str(p), is_png)


def write_card(path: str, card_dict: dict) -> None:
    """Write a card dict back to disk (JSON directly, PNG via re-encoded tEXt)."""
    p = Path(path)
    if p.suffix.lower() == ".png":
        _write_png_card(p, card_dict)
    else:
        p.write_text(
            json.dumps(card_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def extract_schema_dict(card: CharacterCard) -> Optional[dict]:
    """Find the embedded '# 变量初始值' block and parse it into a data-shape dict.

    The block is detected by its content prefix (real cards use arbitrary
    comments such as '[InitVar]请勿打开'), so we scan block contents rather
    than file labels.

    Returns None if no initial-variable block exists or parsing fails
    (caller falls back to degraded mode).
    """
    for block in card.blocks:
        if block.file_type != "worldbook":
            continue
        if block.content.lstrip().startswith("# 变量初始值"):
            try:
                return parse_indented_block(block.content)
            except ValueError:
                return None
    return None


# ── PNG extraction ────────────────────────────────────────────────────


def _extract_png_chara(path: Path) -> dict:
    """Extract the base64-encoded JSON card from the PNG tEXt 'chara' chunk."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("文件不是有效的 PNG 图片")

    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8].decode("latin1")
        cdata = data[pos + 8:pos + 8 + length]
        if ctype == "tEXt":
            idx = cdata.find(b"\x00")
            if idx >= 0 and cdata[:idx].decode("latin1") == "chara":
                raw = cdata[idx + 1:]
                try:
                    decoded = base64.b64decode(raw, validate=False)
                    return json.loads(decoded)
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"PNG 角色卡内嵌 JSON 解析失败: {exc}") from exc
        pos += 12 + length

    raise ValueError("PNG 中未找到 chara 角色卡数据（tEXt chunk 缺失）")


def _chunk_bytes(ctype: str, cdata: bytes) -> bytes:
    return (
        struct.pack(">I", len(cdata))
        + ctype.encode("latin1")
        + cdata
        + struct.pack(">I", 0)  # CRC omitted; tolerated by most readers
    )


def _write_png_card(path: Path, card_dict: dict) -> None:
    """Rebuild the PNG, replacing the chara tEXt chunk with the new JSON."""
    data = path.read_bytes()
    chunks: List[Tuple[str, bytes]] = []
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8].decode("latin1")
        cdata = data[pos + 8:pos + 8 + length]
        if not (ctype == "tEXt" and cdata.find(b"chara\x00") == 0):
            chunks.append((ctype, cdata))
        pos += 12 + length

    raw = json.dumps(card_dict, ensure_ascii=False).encode("utf-8")
    new_text = b"chara\x00" + base64.b64encode(raw)

    out = bytearray(data[:8])
    for ctype, cdata in chunks:
        if ctype == "IEND":
            out += _chunk_bytes("tEXt", new_text)
        out += _chunk_bytes(ctype, cdata)
    path.write_bytes(bytes(out))


# ── Card parsing ──────────────────────────────────────────────────────


def _parse_card(card_json: dict, source: str, is_png: bool) -> CharacterCard:
    if not isinstance(card_json, dict):
        raise ValueError("角色卡 JSON 顶层必须是对象")

    # chara_card_v2: { spec, spec_version, data: {...} }
    data = card_json.get("data")
    if isinstance(data, dict):
        spec = str(card_json.get("spec", ""))
        spec_version = str(card_json.get("spec_version", ""))
        name = str(data.get("name") or card_json.get("name") or "未命名角色卡")
        card = CharacterCard(
            name=name,
            spec=spec,
            spec_version=spec_version,
            data=data,
            source_path=source,
            is_png=is_png,
        )
    elif isinstance(card_json.get("name"), str):
        # Legacy flat card: name/description/... at top level
        card = CharacterCard(
            name=str(card_json["name"]),
            spec="legacy",
            spec_version="",
            data=card_json,
            source_path=source,
            is_png=is_png,
        )
    else:
        raise ValueError("无法识别的角色卡结构（缺少 data 或 name 字段）")

    card.blocks = _build_blocks(card.data)
    return card


# ── Content block extraction ─────────────────────────────────────────


def _pointer(parts: List[Any]) -> str:
    """Build a JSON pointer from path parts (str → key, int → index)."""
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"/{part}"
        else:
            out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _build_blocks(data: dict) -> List[ContentBlock]:
    """Extract every checkable text block from the card data dict."""
    blocks: List[ContentBlock] = []

    # ── Worldbook entries ──────────────────────────────────────────
    chara_book = data.get("character_book") or {}
    entries = chara_book.get("entries") or []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") or ""
        label = entry.get("comment") or entry.get("id") or f"entry_{i:03d}"
        blocks.append(ContentBlock(
            file_path=f"世界书/{label}",
            file_type="worldbook",
            content=content,
            json_pointer=_pointer(["data", "character_book", "entries", i, "content"]),
        ))

    # ── Card text fields ───────────────────────────────────────────
    text_fields = [
        ("first_mes", "开场白"),
        ("description", "描述"),
        ("personality", "性格"),
        ("scenario", "场景"),
        ("mes_example", "示例对话"),
        ("creator_notes", "作者备注"),
        ("system_prompt", "系统提示词"),
        ("post_history_instructions", "历史后置指令"),
    ]
    for key, label in text_fields:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            blocks.append(ContentBlock(
                file_path=f"角色卡/{label}",
                file_type="worldbook",
                content=value,
                json_pointer=_pointer(["data", key]),
            ))

    alt = data.get("alternate_greetings")
    if isinstance(alt, list):
        for i, greeting in enumerate(alt):
            if isinstance(greeting, str) and greeting.strip():
                blocks.append(ContentBlock(
                    file_path=f"角色卡/备用开场白[{i}]",
                    file_type="worldbook",
                    content=greeting,
                    json_pointer=_pointer(["data", "alternate_greetings", i]),
                ))

    # ── Regex scripts ──────────────────────────────────────────────
    ext = data.get("extensions") or {}
    regex_scripts = ext.get("regex_scripts") or []
    for i, script in enumerate(regex_scripts):
        if not isinstance(script, dict):
            continue
        name = script.get("scriptName") or f"regex_{i:03d}"
        find = script.get("findRegex") or ""
        replace = script.get("replaceString") or ""
        combined = f"findRegex:\n{find}\n\nreplaceString:\n{replace}"
        blocks.append(ContentBlock(
            file_path=f"脚本/{name}",
            file_type="script",
            content=combined,
            json_pointer=_pointer(["data", "extensions", "regex_scripts", i]),
        ))

    # ── Depth prompt ───────────────────────────────────────────────
    depth = ext.get("depth_prompt")
    if isinstance(depth, dict):
        prompt = depth.get("prompt") or ""
        if prompt.strip():
            blocks.append(ContentBlock(
                file_path="深度提示/depth_prompt",
                file_type="interface",
                content=prompt,
                json_pointer=_pointer(["data", "extensions", "depth_prompt", "prompt"]),
            ))

    # ── Tavern helper scripts ──────────────────────────────────────
    th = ext.get("tavern_helper") or {}
    th_scripts = th.get("scripts") or []
    for i, script in enumerate(th_scripts):
        if isinstance(script, str) and script.strip():
            blocks.append(ContentBlock(
                file_path=f"脚本/tavern_helper_{i:03d}",
                file_type="script",
                content=script,
                json_pointer=_pointer(["data", "extensions", "tavern_helper", "scripts", i]),
            ))

    return blocks


# ── YAML-ish initial-variable block parser ───────────────────────────


def parse_indented_block(text: str) -> dict:
    """Parse a YAML-ish indented data block (2-space, '- ' list items).

    Handles the shape used by "# 变量初始值" blocks in MVU cards:
      key: value
      key:            → nested dict
      - key: value    → list item (dict)
      - plain         → list item (scalar)
      # comment       → ignored
    Raises ValueError on structural errors (e.g. inconsistent indentation).
    """
    lines = text.splitlines()
    # Drop leading blank lines and the '# 变量初始值' title line
    while lines and (not lines[0].strip() or lines[0].strip().startswith("#")):
        lines.pop(0)

    def _parse_block(idx: int, indent: int) -> Tuple[Any, int]:
        """Parse a block at the given indentation; returns (value, next_idx)."""
        # Peek first real line to decide list vs map
        peek = idx
        while peek < len(lines):
            if lines[peek].strip() and not lines[peek].strip().startswith("#"):
                break
            peek += 1
        if peek >= len(lines):
            return {}, idx

        is_list = lines[peek].lstrip().startswith("- ")
        result: Any = [] if is_list else {}

        while idx < len(lines):
            line = lines[idx]
            if not line.strip() or line.strip().startswith("#"):
                idx += 1
                continue
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent < indent:
                break
            if cur_indent == indent:
                stripped = line.strip()
                if is_list and stripped.startswith("- "):
                    idx = _parse_list_item(idx, indent, result)
                    continue
                if not is_list and not stripped.startswith("- "):
                    idx = _parse_map_key(idx, indent, result)
                    continue
                # Mixed list/map at same indent — stop (parent handles it)
                break
            # Deeper indent with no container key — structural error
            raise ValueError(f"缩进错误（第 {idx + 1} 行）")

        return result, idx

    def _parse_list_item(idx: int, indent: int, result: list) -> int:
        """Parse one '- ...' list item at the given indent; returns next idx."""
        line = lines[idx]
        item_text = line.strip()[2:].strip()
        if not item_text:
            # Nested block on the following lines
            child, next_idx = _parse_block(idx + 1, indent + 2)
            result.append(child)
            return next_idx
        if ":" in item_text:
            key, _, rest = item_text.partition(":")
            key = key.strip().strip("\"'")
            rest = rest.strip()
            item: Dict[str, Any] = {}
            if rest:
                item[key] = _scalar(rest)
                # Continuation fields at deeper indent belong to this item
                nxt = idx + 1
                while nxt < len(lines):
                    ln = lines[nxt]
                    if not ln.strip() or ln.strip().startswith("#"):
                        nxt += 1
                        continue
                    break
                if nxt < len(lines):
                    deeper = len(lines[nxt]) - len(lines[nxt].lstrip(" "))
                    if deeper > indent:
                        child, next_idx = _parse_block(nxt, indent + 2)
                        if isinstance(child, dict):
                            item.update(child)
                        else:
                            raise ValueError(f"列表项字段结构错误（第 {nxt + 1} 行）")
                        result.append(item)
                        return next_idx
                result.append(item)
                return idx + 1
            # '- key:' with nested block
            child, next_idx = _parse_block(idx + 1, indent + 2)
            item[key] = child
            result.append(item)
            return next_idx
        result.append(_scalar(item_text))
        return idx + 1

    def _parse_map_key(idx: int, indent: int, result: dict) -> int:
        """Parse one 'key:' map entry at the given indent; returns next idx."""
        line = lines[idx]
        stripped = line.strip()
        key, sep, rest = stripped.partition(":")
        if not sep:
            raise ValueError(f"缺少冒号的键（第 {idx + 1} 行）")
        key = key.strip().strip("\"'")
        rest = rest.strip()
        if rest:
            result[key] = _scalar(rest)
            return idx + 1
        child, next_idx = _parse_block(idx + 1, indent + 2)
        result[key] = child
        return next_idx

    value, _ = _parse_block(0, 0)
    if not isinstance(value, dict):
        raise ValueError("变量初始值顶层必须是映射")
    return value


def _scalar(text: str) -> Any:
    """Convert a scalar string to bool / number / str."""
    t = text.strip()
    if t.startswith('"') and t.endswith('"') and len(t) >= 2:
        return t[1:-1]
    if t.startswith("'") and t.endswith("'") and len(t) >= 2:
        return t[1:-1]
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t
