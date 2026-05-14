#!/usr/bin/env python3
"""Cross-platform install script for APT Mining Workbench.

Supports Windows and Linux. Creates venv, installs Python deps,
installs frontend deps, builds frontend, and initializes the database.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VENV_DIR = SCRIPT_DIR / "venv"
IS_WINDOWS = platform.system() == "Windows"


def check_prerequisites():
    """Verify Python and Node.js are available."""
    python_ok = False
    try:
        ver = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        print(f"  Python: {ver.stdout.strip()}")
        python_ok = True
    except Exception:
        pass
    if not python_ok:
        print("[ERROR] Python 3.10+ not found. Please install Python first.")
        sys.exit(1)

    node_ok = False
    for cmd_name in ("node", "nodejs"):
        try:
            ver = subprocess.run(
                [cmd_name, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if ver.returncode == 0:
                print(f"  Node.js: {ver.stdout.strip()}")
                node_ok = True
                break
        except FileNotFoundError:
            continue
    if not node_ok:
        print("[ERROR] Node.js 18+ not found. Please install Node.js first.")
        sys.exit(1)


def get_venv_python():
    """Return the path to the virtualenv Python executable."""
    if IS_WINDOWS:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def ensure_venv():
    """Create a virtual environment if one does not exist."""
    venv_python = get_venv_python()
    if venv_python.exists():
        print("  Virtual environment already exists.")
        return venv_python

    print("  Creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

    if not venv_python.exists():
        print("[ERROR] Failed to create virtual environment.")
        sys.exit(1)
    return venv_python


def install_python_deps(venv_python: Path):
    """Install Python dependencies from requirements.txt."""
    print("  Installing Python dependencies...")
    req = SCRIPT_DIR / "requirements.txt"
    # 优先使用阿里云镜像，如果失败则回退到 PyPI
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(req),
         "-i", "https://mirrors.aliyun.com/pypi/simple/"],
        cwd=SCRIPT_DIR,
    )
    if result.returncode != 0:
        print("  [WARN] 阿里云镜像失败，回退到 PyPI 官方源...")
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(req)],
            cwd=SCRIPT_DIR,
        )
    if result.returncode != 0:
        print("[ERROR] Python dependency installation failed.")
        sys.exit(1)


def _get_npm_cmd():
    """Get npm command with registry configured for China."""
    base = "npm.cmd" if IS_WINDOWS else "npm"
    # 使用淘宝 npm 镜像加速
    return [base, "--registry=https://registry.npmmirror.com"]


def install_frontend_deps():
    """Run npm install in the frontend directory."""
    frontend_dir = SCRIPT_DIR / "frontend"
    print("  Installing frontend dependencies...")
    npm_cmd = _get_npm_cmd()
    result = subprocess.run(
        npm_cmd + ["install"],
        cwd=str(frontend_dir),
    )
    if result.returncode != 0:
        print("  [WARN] npmmirror 失败，回退到官方 npm...")
        result = subprocess.run(
            ["npm.cmd" if IS_WINDOWS else "npm", "install"],
            cwd=str(frontend_dir),
        )
    if result.returncode != 0:
        print("[ERROR] Frontend dependency installation failed.")
        sys.exit(1)


def build_frontend():
    """Run npm run build in the frontend directory."""
    frontend_dir = SCRIPT_DIR / "frontend"
    print("  Building frontend...")
    npm_cmd = _get_npm_cmd()
    result = subprocess.run(npm_cmd + ["run", "build"], cwd=str(frontend_dir))
    if result.returncode != 0:
        print("[ERROR] Frontend build failed.")
        sys.exit(1)


def check_database(venv_python: Path):
    """Ensure the database schema is initialized."""
    print("  Checking database...")
    # Add backend to sys.path so the import works
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPT_DIR)
    result = subprocess.run(
        [str(venv_python), "-c", "from backend.utils.db import init_db; init_db(); print('  Database OK')"],
        cwd=SCRIPT_DIR, env=env,
    )
    if result.returncode != 0:
        print("  [WARN] Database check encountered issues. The first run will retry automatically.")


def main():
    separator = "=" * 50
    print(separator)
    print("APT Mining Workbench - Install Runtime")
    print(separator)
    print()

    check_prerequisites()
    print()

    venv_python = ensure_venv()
    install_python_deps(venv_python)
    install_frontend_deps()
    build_frontend()
    check_database(venv_python)

    print()
    print(separator)
    mode_label = "start.bat" if IS_WINDOWS else "./start.sh"
    print(f"Done. Run {mode_label} to launch the workbench.")
    print(separator)


if __name__ == "__main__":
    main()
