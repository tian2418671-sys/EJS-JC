"""CLI entry point: python -m mvu_lint scan <角色卡.zip>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .core.ejs_parser import EJSParser
from .core.project_scanner import ProjectScanner
from .core.schema_loader import SchemaLoader
from .models.check_result import ErrorLevel


def run_scan(zip_path: str) -> dict:
    """Run a full scan on a ZIP archive and return a JSON-serializable report."""
    # 1. Scan ZIP
    scanner = ProjectScanner()
    project = scanner.scan_zip(zip_path)

    # 2. Load schema if available
    schema_info = None
    if project.schema_path and project.schema_form == "json":
        try:
            loader = SchemaLoader()
            schema_info = loader.load_from_json(project.schema_path)
        except Exception as e:
            schema_info = None  # Schema parse failure is non-fatal

    # 3. Run EJS checks on all non-schema files
    parser = EJSParser()
    all_errors = []
    all_var_refs = []
    scanned_count = 0

    for file_entry in project.files:
        if file_entry.file_type == "schema":
            continue
        try:
            with open(file_entry.absolute_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            continue

        # Quick check: does this file contain EJS tags?
        if "<%" not in content:
            continue

        scanned_count += 1
        result = parser.parse(content, file_entry.file_path)
        all_errors.extend(result.check_results)
        all_var_refs.extend(result.variable_refs)

    # 4. Build report
    report = {
        "project": project.to_dict(),
        "schema": {
            "found": schema_info is not None,
            "form": schema_info.form if schema_info else None,
            "path_count": len(schema_info.paths) if schema_info else 0,
            "paths": (
                [p.path for p in schema_info.paths[:20]]
                if schema_info else []
            ),
        },
        "scan": {
            "files_scanned": scanned_count,
            "total_files": len(project.files),
        },
        "errors": [e.to_dict() for e in all_errors],
        "variable_refs": [
            {
                "raw": ref.raw,
                "path": ref.path,
                "line": ref.line,
                "is_safe": ref.is_safe,
                "is_static": ref.is_static,
                "note": ref.note,
                "file": ref.raw,  # placeholder; file is in the error
            }
            for ref in all_var_refs
        ],
        "summary": {
            "total_errors": len(all_errors),
            "lv1_count": sum(1 for e in all_errors if e.level == ErrorLevel.LV1),
            "lv2_count": sum(1 for e in all_errors if e.level == ErrorLevel.LV2),
            "lv3_count": sum(1 for e in all_errors if e.level == ErrorLevel.LV3),
            "lv4_count": sum(1 for e in all_errors if e.level == ErrorLevel.LV4),
            "total_var_refs": len(all_var_refs),
            "static_var_refs": sum(1 for r in all_var_refs if r.is_static),
            "blocking": sum(1 for e in all_errors if e.level in
                            (ErrorLevel.LV1, ErrorLevel.LV2, ErrorLevel.LV3)),
        },
    }
    return report


def main():
    """CLI main entry point."""
    if len(sys.argv) < 2:
        print("用法: python -m mvu_lint [scan <角色卡.zip> | gui]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "scan":
        if len(sys.argv) < 3:
            print("用法: python -m mvu_lint scan <角色卡.zip>")
            sys.exit(1)
        zip_path = sys.argv[2]
        if not Path(zip_path).exists():
            print(f"错误: 文件不存在: {zip_path}")
            sys.exit(1)
        report = run_scan(zip_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif cmd == "gui":
        try:
            from .app import main as gui_main
        except ImportError as exc:
            print(f"错误: GUI 依赖缺失（需要 PySide6）: {exc}")
            sys.exit(1)
        sys.exit(gui_main())
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: scan, gui")
        sys.exit(1)


if __name__ == "__main__":
    main()
