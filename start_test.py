#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    env = os.environ.copy()
    env.setdefault("APT_SERVER_HOST", "127.0.0.1")
    env.setdefault("APT_SERVER_PORT", "9099")
    env.setdefault("APT_DB_PATH", "./data/workbench-test.db")
    env.setdefault("APT_UPLOAD_TMP", "./uploads-test")
    env.setdefault("VITE_API_TARGET", f"http://{env['APT_SERVER_HOST']}:{env['APT_SERVER_PORT']}")
    env.setdefault("APT_AUTO_OPEN_BROWSER", "1")

    print("======================================")
    print("APT Mining Workbench - Test Mode")
    print("======================================")
    print(f"Backend: http://{env['APT_SERVER_HOST']}:{env['APT_SERVER_PORT']}")
    print(f"Test DB: {env['APT_DB_PATH']}")
    print(f"Test Uploads: {env['APT_UPLOAD_TMP']}")

    cmd = [sys.executable, str(SCRIPT_DIR / "start.py")]
    completed = subprocess.run(cmd, cwd=SCRIPT_DIR, env=env)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
