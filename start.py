#!/usr/bin/env python3
"""Cross-platform start script for APT Mining Workbench.

Usage:
    python start.py [--test]

Supports Windows and Linux. Detects platform for venv path, port check,
and browser auto-open. In test mode, uses isolated port/DB/uploads.
"""
import argparse
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
IS_WINDOWS = platform.system() == "Windows"


def get_venv_python():
    """Return the path to the virtualenv Python executable."""
    if IS_WINDOWS:
        return SCRIPT_DIR / "venv" / "Scripts" / "python.exe"
    return SCRIPT_DIR / "venv" / "bin" / "python3"


def ensure_runtime_ready():
    venv_python = get_venv_python()
    if not venv_python.exists():
        installer = "install.bat" if IS_WINDOWS else "./install.sh"
        print(f"[ERROR] Virtual env not found. Please run {installer} first.")
        sys.exit(1)
    if not (SCRIPT_DIR / "frontend" / "dist" / "index.html").exists():
        print("[ERROR] frontend/dist/index.html not found. The runtime package is incomplete.")
        sys.exit(1)
    return venv_python


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def kill_existing_on_port(host: str, port: int):
    """Attempt to kill any process listening on the given port."""
    if IS_WINDOWS:
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                (f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                 "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            pids = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
            for pid in pids:
                print(f"  Staling process PID={pid} on port {port}, killing...")
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        except Exception:
            pass
    else:
        # Linux: try lsof, then fuser as fallback
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    pid = line.strip()
                    if pid.isdigit():
                        print(f"  Staling process PID={pid} on port {port}, killing...")
                        os.kill(int(pid), 9)
                        print(f"  Killed PID={pid}")
        except FileNotFoundError:
            try:
                subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
                print(f"  Killed process on port {port} via fuser")
            except FileNotFoundError:
                print(f"  [WARN] Neither lsof nor fuser found. Cannot kill process on port {port}.")
            except Exception:
                pass
        except Exception:
            pass


def open_browser(host: str, port: int):
    try:
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")
    except Exception:
        if not IS_WINDOWS:
            # Linux fallback: xdg-open
            try:
                subprocess.Popen(["xdg-open", f"http://{host}:{port}"])
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Start APT Mining Workbench")
    parser.add_argument("--test", action="store_true", help="Run in test mode (port 9099, isolated DB)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--host", type=str, default=None, help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port number (default: 8088 or 9099 for test)")
    args = parser.parse_args()

    venv_python = ensure_runtime_ready()

    # Determine mode
    if args.test:
        host = args.host or os.environ.get("APT_SERVER_HOST", "127.0.0.1")
        port = args.port or int(os.environ.get("APT_SERVER_PORT", "9099"))
        db_path = os.environ.get("APT_DB_PATH", "./data/workbench-test.db")
        upload_tmp = os.environ.get("APT_UPLOAD_TMP", "./uploads-test")
    else:
        host = args.host or os.environ.get("APT_SERVER_HOST", "127.0.0.1")
        port = args.port or int(os.environ.get("APT_SERVER_PORT", "8088"))
        db_path = os.environ.get("APT_DB_PATH", "./data/workbench.db")
        upload_tmp = os.environ.get("APT_UPLOAD_TMP", "./uploads")

    auto_open = not args.no_browser and os.environ.get("APT_AUTO_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}

    # Ensure directories exist
    os.makedirs(SCRIPT_DIR / "data", exist_ok=True)
    if upload_tmp:
        os.makedirs(SCRIPT_DIR / upload_tmp, exist_ok=True)

    # Build environment
    env = os.environ.copy()
    env["APT_SERVER_HOST"] = host
    env["APT_SERVER_PORT"] = str(port)
    env["APT_DB_PATH"] = db_path
    env["APT_UPLOAD_TMP"] = upload_tmp
    env["PYTHONPATH"] = str(SCRIPT_DIR)
    if not args.test:
        env.setdefault("VITE_API_TARGET", f"http://{host}:{port}")

    mode_label = "Test Mode" if args.test else "Starting"
    print("======================================")
    print(f"APT Mining Workbench - {mode_label}")
    print("======================================")
    print(f"Backend: http://{host}:{port}")
    if args.test:
        print(f"Test DB: {db_path}")
        print(f"Test Uploads: {upload_tmp}")

    if port_in_use(host, port):
        print(f"Port {port} is in use. Attempting to free it...")
        kill_existing_on_port(host, port)
        import time
        time.sleep(0.5)
        if port_in_use(host, port):
            print(f"[ERROR] Port {port} is still in use.")
            sys.exit(1)

    if auto_open:
        open_browser(host, port)

    cmd = [
        str(venv_python), "-m", "uvicorn",
        "backend.main:app",
        "--host", host, "--port", str(port),
        "--timeout-keep-alive", "600",
    ]
    print(f"Launching uvicorn: {' '.join(cmd)}")
    print()
    completed = subprocess.run(cmd, cwd=SCRIPT_DIR, env=env)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
