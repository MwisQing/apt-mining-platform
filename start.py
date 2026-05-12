#!/usr/bin/env python3
import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = SCRIPT_DIR / "venv" / "Scripts" / "python.exe"


def ensure_runtime_ready():
    if not VENV_PYTHON.exists():
        print("[ERROR] Virtual env not found. Please run install.bat first.")
        sys.exit(1)
    if not (SCRIPT_DIR / "frontend" / "dist" / "index.html").exists():
        print("[ERROR] frontend/dist/index.html not found. The runtime package is incomplete.")
        sys.exit(1)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def main():
    ensure_runtime_ready()
    host = os.environ.get("APT_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("APT_SERVER_PORT", "8088"))
    auto_open = os.environ.get("APT_AUTO_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}

    print("======================================")
    print("APT Mining Workbench - Starting")
    print("======================================")
    print(f"Backend: http://{host}:{port}")

    if port_in_use(host, port):
        print(f"[ERROR] Port {port} is already in use.")
        sys.exit(1)

    if auto_open:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass

    cmd = [str(VENV_PYTHON), "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)]
    completed = subprocess.run(cmd, cwd=SCRIPT_DIR)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
