#!/usr/bin/env python3
"""Quick start test instance — port 9099, apt_mining_test."""
import subprocess, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.exit(subprocess.run([sys.executable, str(SCRIPT_DIR / "start.py"), "--test"]).returncode)
