"""Smoke test: launch the packaged exe (NO args, like a double-click),
confirm it stays alive (event loop running), then kill it."""
import os
import subprocess
import sys
import time

EXE = r"E:\AI\酒馆工具\JSK管理APP\方案1\dist\MvuEjsLinter.exe"

env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["PYTHONUNBUFFERED"] = "1"

proc = subprocess.Popen([EXE], env=env)
time.sleep(8)

if proc.poll() is not None:
    print(f"[FAIL] exe exited early with code {proc.returncode}")
    sys.exit(1)

print("[OK]   exe is running (event loop alive after 8s, no args needed)")
proc.terminate()
try:
    proc.wait(timeout=10)
    print(f"[OK]   exe terminated cleanly (code {proc.returncode})")
except subprocess.TimeoutExpired:
    proc.kill()
    print("[WARN] exe did not exit after terminate; killed")