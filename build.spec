# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec — MVU + EJS 智能检查工具
#
# Build command:
#   pyinstaller build.spec --noconfirm
#
# Entry point:
#   gui_launcher.py — packaged exe always launches the GUI on double-click
#   (dev mode keeps `python -m mvu_lint scan|gui`).
#
# Native binary handling (SPEC Appendix B):
#   - sqlite-vec: vec0.dll / vec0.so must sit next to the bundled sqlite3
#   - llama-cpp-python: wheel ships its own DLLs; --hidden-import keeps
#     PyInstaller from pruning the module. (Not installed yet — optional AI
#     dependency, Phase 5+. collect_dynamic_libs returns [] gracefully.)
#
# Wine note: llama-cpp-python DLLs are located at runtime via the package
# dir; keep `collect_dynamic_libs` so they are copied next to the exe.

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

# sqlite-vec prebuilt binaries from the wheel
sqlite_vec_binaries = collect_dynamic_libs("sqlite_vec")
sqlite_vec_datas = collect_data_files("sqlite_vec")

# llama-cpp-python native libs (llama.dll / libllama.so / ggml libs)
llama_binaries = collect_dynamic_libs("llama_cpp")

hiddenimports = [
    "llama_cpp",
    "sqlite_vec",
    "numpy",
]

datas = sqlite_vec_datas + [("resources", "resources")]

binaries = sqlite_vec_binaries + llama_binaries

a = Analysis(
    ["gui_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "scipy",
        "pandas",
        "PIL",
        "PySide6.QtWebEngineCore",  # 不需要浏览器内核
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MvuEjsLinter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 可能破坏 llama.dll / vec0.dll，关闭
    console=False,       # GUI 应用
    disable_windowed_traceback=False,
    icon="resources/icon.ico",
    version=None,
)