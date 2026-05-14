#!/usr/bin/env python3
"""Cross-platform stop script for APT Mining Workbench.

Usage:
    python stop.py [--test] [--port PORT]

Supports Windows and Linux. Detects platform for port-based process kill.
"""
import argparse
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
SCRIPT_DIR = Path(__file__).resolve().parent


def kill_pid_file():
    """Kill process by PID file (daemon mode)."""
    pid_file = SCRIPT_DIR / "backend.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return False

    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True,
            )
            if str(pid) in result.stdout:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                print(f"  Killed daemon PID={pid} (from PID file)")
                pid_file.unlink(missing_ok=True)
                return True
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 0)  # check if alive
            os.kill(pid, 9)
            print(f"  Killed daemon PID={pid} (from PID file)")
            pid_file.unlink(missing_ok=True)
            return True
        except ProcessLookupError:
            print(f"  Daemon PID={pid} already exited.")
            pid_file.unlink(missing_ok=True)
            return True
        except PermissionError:
            print(f"  Permission denied for daemon PID={pid}. Try sudo.")
            return False
    return False


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def get_pids_on_port(port: int):
    """Return a list of PIDs listening on the given TCP port."""
    if IS_WINDOWS:
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                (f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                 "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            pids = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
            return sorted(pids)
        except Exception as exc:
            print(f"  [WARN] PowerShell port query failed: {exc}")
            return []
    else:
        # Linux: try lsof, then fuser as fallback
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                pids = set()
                for line in result.stdout.strip().splitlines():
                    pid = line.strip()
                    if pid.isdigit():
                        pids.add(int(pid))
                return sorted(pids)
        except FileNotFoundError:
            pass

        # Fallback: fuser
        try:
            result = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True, text=True, timeout=5,
            )
            # fuser outputs PIDs like " 12345"
            pids = set()
            for token in result.stdout.strip().split():
                token = token.strip()
                if token.isdigit():
                    pids.add(int(token))
            return sorted(pids)
        except FileNotFoundError:
            print("  [WARN] Neither lsof nor fuser found. Cannot auto-detect PIDs.")
            return []
        except Exception:
            return []


def kill_process(pid: int):
    """Kill a process by PID using the platform-appropriate method."""
    if IS_WINDOWS:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  Killed PID={pid}")
        else:
            print(f"  [WARN] Failed to kill PID={pid}: {result.stderr.strip()}")
    else:
        try:
            os.kill(pid, 9)
            print(f"  Killed PID={pid}")
        except ProcessLookupError:
            print(f"  PID={pid} already exited.")
        except PermissionError:
            print(f"  [ERROR] Permission denied for PID={pid}. Try with sudo.")
        except Exception as exc:
            print(f"  [WARN] Failed to kill PID={pid}: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Stop APT Mining Workbench")
    parser.add_argument("--test", action="store_true", help="Stop test instance (port 9099)")
    parser.add_argument("--port", type=int, default=None, help="Port to stop (overrides default)")
    parser.add_argument("--all", action="store_true", help="Stop both production and test instances")
    args = parser.parse_args()

    print("======================================")
    print("APT Mining Workbench - Stop Service")
    print("======================================")

    # Try PID file first (daemon mode)
    if not args.port and not args.test:
        if kill_pid_file():
            return

    ports_to_check = []
    if args.all:
        ports_to_check = [8088, 9099]
    elif args.test:
        ports_to_check = [args.port or 9099]
    else:
        ports_to_check = [args.port or 8088]

    found_any = False
    for port in ports_to_check:
        host = "127.0.0.1"
        if not port_in_use(host, port):
            if len(ports_to_check) > 1:
                print(f"Port {port}: No service running.")
            else:
                print(f"No running service found on port {port}.")
            continue

        pids = get_pids_on_port(port)
        if not pids:
            # Port is in use but we couldn't find the PID
            print(f"Port {port} is in use, but could not identify the process.")
            print(f"  Try: lsof -ti tcp:{port} | xargs kill -9  (Linux)")
            print(f"  Try: netstat -ano | findstr :{port}         (Windows)")
            found_any = True
            continue

        found_any = True
        print(f"Port {port}: {len(pids)} process(es) found.")
        for pid in pids:
            kill_process(pid)

    if not found_any:
        print("No running services found on the target port(s).")
    else:
        print()
        print("Service stopped.")


if __name__ == "__main__":
    main()
