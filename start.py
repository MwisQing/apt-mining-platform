#!/usr/bin/env python3
"""Cross-platform start script for APT Mining Workbench v4.0 (Go backend).

Usage:
    python start.py [--test]

Supports Windows and Linux. Detects platform for port check and browser auto-open.
In test mode, uses isolated port/DB/uploads.
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


def go_env(go_dir: Path) -> dict:
    """Keep Go build cache inside the repo to avoid host cache permission issues."""
    env = os.environ.copy()
    cache_dir = go_dir / ".gocache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    env.setdefault("GOCACHE", str(cache_dir))
    return env


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
            try:
                subprocess.Popen(["xdg-open", f"http://{host}:{port}"])
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Start APT Mining Workbench v4.0 (Go)")
    parser.add_argument("--test", action="store_true", help="Run in test mode (port 9099, isolated DB)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--host", type=str, default=None, help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port number (default: 8088 or 9099 for test)")
    args = parser.parse_args()

    default_host = "127.0.0.1"
    host = args.host or default_host
    port = args.port or (9099 if args.test else 8088)

    # Load .env file if present
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        os.environ.setdefault(key, value)

    auto_open = not args.no_browser and os.environ.get("APT_AUTO_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}

    mode_label = "Test Mode" if args.test else "Starting"
    print("======================================")
    print(f"APT Mining Workbench v4.0 - {mode_label}")
    print("======================================")
    print(f"Backend: http://{host}:{port}")
    if args.test:
        print(f"DB: apt_mining_test")
    else:
        print(f"DB: apt_mining_prod")

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

    # Launch Go backend
    go_dir = SCRIPT_DIR / "backend_v2"
    go_exe = go_dir / ("apt-mining.exe" if IS_WINDOWS else "apt-mining")
    if not go_exe.exists():
        print("Go binary not found. Building...")
        go_build_env = go_env(go_dir)
        result = subprocess.run(
            ["go", "build", "-o", str(go_exe), "."],
            cwd=str(go_dir), capture_output=True, text=True, env=go_build_env,
        )
        if result.returncode != 0:
            print(f"[ERROR] Go build failed:\n{result.stderr}")
            sys.exit(1)
        print("Go build complete.")

    # Set environment for Go backend
    env = os.environ.copy()
    env["APT_SERVER_HOST"] = host
    env["APT_SERVER_PORT"] = str(port)
    env["APT_DB_HOST"] = os.environ.get("APT_DB_HOST", "127.0.0.1")
    env["APT_DB_PORT"] = os.environ.get("APT_DB_PORT", "5432")
    if args.test:
        env["APT_DB_NAME"] = os.environ.get("APT_DB_NAME_TEST", "apt_mining_test")
        env["APT_DB_USER"] = os.environ.get("APT_DB_USER_TEST", "apt_test")
        env["APT_DB_PASSWORD"] = os.environ.get("APT_DB_PASSWORD_TEST", "")
    else:
        env["APT_DB_NAME"] = os.environ.get("APT_DB_NAME_PROD", "apt_mining_prod")
        env["APT_DB_USER"] = os.environ.get("APT_DB_USER_PROD", "apt_prod")
        env["APT_DB_PASSWORD"] = os.environ.get("APT_DB_PASSWORD_PROD", "")
    env["APT_UPLOAD_TMP"] = str(SCRIPT_DIR / ("uploads-test" if args.test else "uploads"))

    os.makedirs(env["APT_UPLOAD_TMP"], exist_ok=True)

    cmd = [str(go_exe)]
    print(f"Launching: {go_exe}")
    print()
    completed = subprocess.run(cmd, cwd=str(go_dir), env=env)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
