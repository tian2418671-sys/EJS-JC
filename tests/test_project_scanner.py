"""Unit tests for ProjectScanner (character card import)."""
import json
import pytest
from mvu_lint.core.project_scanner import ProjectScanner


def _card_dict():
    """Minimal chara_card_v2 JSON card used across scanner tests."""
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "测试角色卡",
        "data": {
            "name": "测试角色卡",
            "description": "测试卡",
            "first_mes": "你好",
            "extensions": {},
            "character_book": {
                "name": "世界书",
                "entries": [
                    {"id": "e1", "keys": ["测试"], "comment": "条目一",
                     "content": "<%= data.x %>", "enabled": True},
                    {"id": "e2", "keys": [], "comment": "条目二",
                     "content": "<!-- mvu: 主角.好感度 += 1 -->", "enabled": True},
                ],
            },
        },
    }


def _write_card(tmp_path, name="card.json"):
    path = tmp_path / name
    path.write_text(json.dumps(_card_dict(), ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_scan_json_card_finds_blocks(tmp_path):
    """A JSON card should be indexed into content blocks (worldbook etc.)."""
    scanner = ProjectScanner()
    project = scanner.scan_card(_write_card(tmp_path))

    assert project.source.endswith("card.json")
    assert len(project.files) >= 4  # 2 worldbook + first_mes + description

    types = {f.file_path: f.file_type for f in project.files}
    assert types.get("世界书/条目一") == "worldbook"
    assert types.get("世界书/条目二") == "worldbook"
    assert types.get("角色卡/开场白") == "worldbook"
    assert types.get("角色卡/描述") == "worldbook"

    # Content lives in memory (no disk file to open)
    entry = next(f for f in project.files if f.file_path == "世界书/条目一")
    assert entry.content == "<%= data.x %>"
    assert entry.json_pointer == "/data/character_book/entries/0/content"


def test_scan_png_card_rejected_cleanly(tmp_path):
    """A random PNG without a chara chunk should raise a clear error."""
    png = tmp_path / "empty.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    scanner = ProjectScanner()
    with pytest.raises(ValueError, match="chara"):
        scanner.scan_card(str(png))


def test_unsupported_format_rejected(tmp_path):
    """ZIP / other extensions must be rejected with a clear message."""
    zip_path = tmp_path / "card.zip"
    zip_path.write_bytes(b"PK\x03\x04")
    scanner = ProjectScanner()
    with pytest.raises(ValueError, match="zip"):
        scanner.scan_card(str(zip_path))


def test_legacy_flat_card_supported(tmp_path):
    """Legacy flat cards (no spec/data wrapper) should still import."""
    flat = {"name": "旧卡", "description": "旧格式", "first_mes": "<%= data.x %>"}
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(flat, ensure_ascii=False), encoding="utf-8")

    scanner = ProjectScanner()
    project = scanner.scan_card(str(path))
    assert project.card is not None
    assert project.card.spec == "legacy"
    assert any(f.file_path == "角色卡/开场白" for f in project.files)


def test_scan_directory_deprecated():
    """Directory scanning is gone — cards are files now."""
    scanner = ProjectScanner()
    with pytest.raises(NotImplementedError):
        scanner.scan_directory("some_dir")
