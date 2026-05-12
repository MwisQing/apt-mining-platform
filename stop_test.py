#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    cmd = [sys.executable, str(SCRIPT_DIR / "stop.py"), "9099"]
    completed = subprocess.run(cmd, cwd=SCRIPT_DIR)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
