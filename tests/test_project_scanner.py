"""Unit tests for ProjectScanner."""
import json
import zipfile
import pytest
from mvu_lint.core.project_scanner import ProjectScanner


def test_scan_zip_finds_files(tmp_path):
    """ZIP extraction should find all project files."""
    zip_path = tmp_path / "test_card.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("schema.json", json.dumps({"主角": {"好感度": 0}}))
        zf.writestr("世界书/entry1.json", '{"content": "<%= data.x %>"}')
        zf.writestr("脚本/script.js", 'console.log("test");')
        zf.writestr("界面/ui.html", '<div>hello</div>')

    scanner = ProjectScanner()
    project = scanner.scan_zip(str(zip_path))

    assert project.schema_path is not None
    assert project.schema_path.endswith("schema.json")
    assert project.schema_form == "json"
    assert len(project.files) >= 4

    types = {f.file_path: f.file_type for f in project.files}
    assert types.get("schema.json") == "schema"
    assert types.get("世界书/entry1.json") == "worldbook"
    assert types.get("脚本/script.js") == "script"
    assert types.get("界面/ui.html") == "interface"


def test_schema_ts_fallback(tmp_path):
    """When only schema.ts exists, it should be detected with form='ts'."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("schema.ts", "export const Schema = z.object({})")

    scanner = ProjectScanner()
    project = scanner.scan_zip(str(zip_path))
    assert project.schema_path is not None
    assert project.schema_form == "ts"


def test_nested_directory_structure(tmp_path):
    """Files in nested directories should be found via recursive scan."""
    zip_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("角色卡/schema.json", '{}')
        zf.writestr("角色卡/世界书/deep/nested/entry.json", '{}')

    scanner = ProjectScanner()
    project = scanner.scan_zip(str(zip_path))
    assert project.schema_path is not None
    file_paths = [f.file_path for f in project.files]
    assert any("nested/entry.json" in p for p in file_paths)
