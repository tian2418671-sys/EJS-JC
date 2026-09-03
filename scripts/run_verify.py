"""Helper to capture stdout from the packaged exe."""
import subprocess
import sys

exe = r"E:\AI\酒馆工具\JSK管理APP\方案1\dist\MvuEjsLinter.exe"
proc = subprocess.run([exe, "--verify-binaries"], capture_output=True)
print("returncode:", proc.returncode)
print("STDOUT bytes:")
print(proc.stdout)
print("STDERR bytes:")
print(proc.stderr)
for enc in ("utf-8", "gbk", "utf-8-sig"):
    try:
        print(f"\n--- decode {enc} ---")
        print("STDOUT:", proc.stdout.decode(enc))
        print("STDERR:", proc.stderr.decode(enc))
    except UnicodeDecodeError as e:
        print(f"decode {enc} failed:", e)
sys.exit(proc.returncode)
