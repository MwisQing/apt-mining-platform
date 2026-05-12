#!/usr/bin/env python3
import subprocess
import sys


def get_pids_on_port(port: int):
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    pids = get_pids_on_port(port)
    print("======================================")
    print("APT Mining Workbench - Stop Service")
    print("======================================")
    if not pids:
        print(f"No running service found on port {port}.")
        return
    for pid in pids:
        print(f"Stopping process on port {port}: {pid}")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    print("Service stopped.")


if __name__ == "__main__":
    main()
