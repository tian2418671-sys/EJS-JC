"""PyInstaller 打包入口：双击 dist/MvuEjsLinter.exe 直接启动 GUI。

开发模式仍用 `python -m mvu_lint scan|gui`。
本文件仅服务于打包分发（build.spec 的 Analysis 入口）。

额外约定：
  MvuEjsLinter.exe --verify-binaries   执行二进制组件验证
"""
import io
import sys

if sys.platform == "win32" and not hasattr(sys, "frozen"):
    # Dev mode: keep default console encoding. Frozen exe stdout is a pipe with
    # cp936/cp1252; re-wrap to UTF-8 so Chinese diagnostics display correctly.
    pass
elif sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def _verify_binaries() -> int:
    """Run the same checks as scripts/verify_binaries.py from inside the bundle."""
    import ctypes
    import platform
    import sqlite3

    def check_sqlite_vec() -> bool:
        try:
            conn = sqlite3.connect(":memory:")
            conn.enable_load_extension(True)
            try:
                import sqlite_vec
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
        try:
            from llama_cpp import llama_cpp
            lib = llama_cpp
            handle = ctypes.CDLL(lib.__file__)
            print(f"[OK]   llama-cpp-python DLL loaded: {lib.__file__}")
            del handle
            return True
        except ImportError as exc:
            print(f"[SKIP] llama-cpp-python not bundled (optional): {exc}")
            return True
        except Exception as exc:
            print(f"[FAIL] llama-cpp-python DLL load failed: {exc}")
            return False

    def check_ui_imports() -> bool:
        try:
            import PySide6
            print(f"[OK]   PySide6 version: {getattr(PySide6, '__version__', '?')}")
            return True
        except Exception as exc:
            print(f"[FAIL] PySide6 import failed: {exc}")
            return False

    print(f"平台: {platform.platform()} / {platform.architecture()[0]}")
    print(f"Python: frozen={getattr(sys, 'frozen', False)}")
    print("-" * 60)
    results = [check_sqlite_vec(), check_llama_cpp(), check_ui_imports()]
    print("-" * 60)
    if all(results):
        print("全部二进制验证通过。")
        return 0
    print("存在失败项 — 请检查 build.spec 的二进制收集配置。")
    print("SQLite-vec 失败时应用仍可运行（自动降级到 NumPy 暴力检索）。")
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--verify-binaries", "--verify"):
        sys.exit(_verify_binaries())

    from mvu_lint.app import main
    sys.exit(main())