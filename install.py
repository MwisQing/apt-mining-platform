#!/usr/bin/env python3
"""Cross-platform install script for APT Mining Workbench v4.0 (Go backend).

Supports Windows and Linux.
1. Verifies Go and Node.js are available
2. Builds Go backend binary
3. Installs frontend deps and builds frontend
4. Initializes PostgreSQL database
"""
import os
import platform
import shutil
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


def check_go():
    """Verify Go is available."""
    try:
        ver = subprocess.run(
            ["go", "version"],
            capture_output=True, text=True, timeout=5,
        )
        print(f"  Go: {ver.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("  [ERROR] Go not found. Install from https://go.dev/dl/")
        return False
    except Exception:
        return False


def check_node():
    """Verify Node.js is available."""
    try:
        ver = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        print(f"  Node.js: {ver.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("  [ERROR] Node.js not found. Install from https://nodejs.org/")
        return False
    except Exception:
        return False


def build_go():
    """Build Go backend binary."""
    go_dir = SCRIPT_DIR / "backend_v2"
    if not (go_dir / "go.mod").exists():
        print("  [ERROR] backend_v2/go.mod not found")
        return False
    env = go_env(go_dir)

    # Download dependencies
    print("  Downloading Go dependencies...")
    result = subprocess.run(
        ["go", "mod", "download"],
        cwd=str(go_dir), capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"  [WARN] go mod download: {result.stderr.strip()}")

    # Build
    exe_name = "apt-mining.exe" if IS_WINDOWS else "apt-mining"
    go_exe = go_dir / exe_name
    print(f"  Building {exe_name}...")
    result = subprocess.run(
        ["go", "build", "-o", str(go_exe), "."],
        cwd=str(go_dir), capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"  [ERROR] Go build failed:\n{result.stderr}")
        return False
    print(f"  OK: {go_exe}")
    return True


def build_frontend():
    """Install frontend deps and build."""
    frontend_dir = SCRIPT_DIR / "frontend"
    pkg_json = frontend_dir / "package.json"
    if not pkg_json.exists():
        print("  [WARN] frontend/package.json not found, skipping frontend")
        return True

    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        print("  Installing frontend dependencies...")
        result = subprocess.run(
            "npm install --registry=https://registry.npmmirror.com",
            shell=True, cwd=str(frontend_dir),
        )
        if result.returncode != 0:
            print("  [ERROR] npm install failed")
            return False

    print("  Building frontend...")
    result = subprocess.run(
        "npx vite build",
        shell=True, cwd=str(frontend_dir),
    )
    if result.returncode != 0:
        print("  [ERROR] frontend build failed")
        return False
    print("  OK: frontend/dist/")
    return True


def check_database():
    """Initialize PostgreSQL tables."""
    migrations = SCRIPT_DIR / "backend_v2" / "migrations" / "001_initial.up.sql"
    if not migrations.exists():
        print("  [WARN] Migration file not found, skipping DB init")
        return True

    print("  Run init_db.bat (Windows) or apply migrations manually")
    return True


def main():
    print("=" * 40)
    print("APT Mining Workbench v4.0 - Install")
    print("=" * 40)

    # 1. Check prerequisites
    print("\n[1/4] Checking prerequisites...")
    if not check_go():
        sys.exit(1)
    check_node()  # optional for production

    # 2. Build Go backend
    print("\n[2/4] Building Go backend...")
    if not build_go():
        sys.exit(1)

    # 3. Build frontend
    print("\n[3/4] Building frontend...")
    if not build_frontend():
        print("  Continuing without frontend...")

    # 4. Database
    print("\n[4/4] Database...")
    check_database()

    print("\n" + "=" * 40)
    print("Install complete!")
    print("  Start:  python start.py")
    print("  Test:   python start.py --test")
    print("  Stop:   python stop.py")
    print("=" * 40)


if __name__ == "__main__":
    main()
