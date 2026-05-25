#!/usr/bin/env python3
"""Quick stop test instance — port 9099."""
import subprocess, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.exit(subprocess.run([sys.executable, str(SCRIPT_DIR / "stop.py"), "--test"]).returncode)
