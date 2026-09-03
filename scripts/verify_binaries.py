"""Binary collection verification script (Appendix B of SPEC).

Run INSIDE the PyInstaller build (or unpacked dist) to confirm that
native extensions were collected correctly:

    python verify_binaries.py

Checks:
  1. sqlite-vec (vec0) can be loaded by the bundled sqlite3
  2. llama-cpp-python (llama.dll) can be loaded via ctypes
  3. UI imports (PySide6) resolve

Exit code 0 → all binaries OK. Non-zero → at least one check failed.
"""
from __future__ import annotations

import ctypes
import importlib
import platform
import sqlite3
import sys


def check_sqlite_vec() -> bool:
    """Try loading vec0 via the sqlite-vec package (or raw extension)."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        try:
            import sqlite_vec  # prefer the python package loader

            sqlite_vec.load(conn)
        except ImportError:
            conn.load_extension("vec0")
        version = conn.execute("SELECT vec_version()").fetchone()
        print(f"[OK]   sqlite-vec version: {version[0] if version else 'unknown'}")
        conn.close()
        return True
    except Exception as exc:
        print(f"[FAIL] sqlite-vec load failed: {exc}")
        return False


def check_llama_cpp() -> bool:
    """Verify llama-cpp-python native lib is loadable.

    Uses ctypes so we don't need a real .gguf model file.
    """
    try:
        from llama_cpp import llama_cpp

        lib = llama_cpp
        # Force loading of the underlying DLL through ctypes
        handle = ctypes.CDLL(lib.__file__)
        print(f"[OK]   llama-cpp-python DLL loaded: {lib.__file__}")
        del handle
        return True
    except ImportError as exc:
        print(f"[SKIP] llama-cpp-python not bundled (optional): {exc}")
        return True  # optional component — not a hard failure
    except Exception as exc:
        print(f"[FAIL] llama-cpp-python DLL load failed: {exc}")
        return False


def check_ui_imports() -> bool:
    """Verify the GUI stack imports cleanly (catches missing hidden imports)."""
    try:
        import PySide6  # noqa: F401

        print(f"[OK]   PySide6 version: {getattr(PySide6, '__version__', '?')}")
        return True
    except Exception as exc:
        print(f"[FAIL] PySide6 import failed: {exc}")
        return False


def main() -> int:
    print(f"平台: {platform.platform()} / {platform.architecture()[0]}")
    print(f"Python: {sys.version.split()[0]}  (bundled: {getattr(sys, 'frozen', False)})")
    print("-" * 60)

    results = [
        check_sqlite_vec(),
        check_llama_cpp(),
        check_ui_imports(),
    ]

    print("-" * 60)
    if all(results):
        print("全部二进制验证通过。")
        return 0
    print("存在失败项 — 请检查 build.spec 的二进制收集配置。")
    print("SQLite-vec 失败时应用仍可运行（自动降级到 NumPy 暴力检索）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())