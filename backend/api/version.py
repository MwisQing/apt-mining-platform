import os
import subprocess
from fastapi import APIRouter

router = APIRouter()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_version():
    ver_path = os.path.join(_PROJECT_ROOT, "VERSION")
    if os.path.exists(ver_path):
        with open(ver_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "unknown"


def _get_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_git_remote_url():
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _check_update_available():
    """Compare local HEAD with remote HEAD. Returns (has_update, local_ahead)."""
    remote = _get_git_remote_url()
    if not remote:
        return False, False
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, cwd=_PROJECT_ROOT, timeout=30
        )
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        ).stdout.strip()
        remote_head = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        ).stdout.strip()
        if not local or not remote_head:
            return False, False
        if local == remote_head:
            return False, False
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", remote_head, local],
            cwd=_PROJECT_ROOT, timeout=5
        )
        if result.returncode == 0:
            return False, True  # local is ahead
        return True, False  # remote is ahead
    except Exception:
        return False, False


@router.get("/api/version")
def get_version():
    commit = _get_git_commit()
    remote_url = _get_git_remote_url()
    has_update, local_ahead = _check_update_available()
    return {
        "version": _read_version(),
        "git_commit": commit,
        "git_remote_url": remote_url,
        "update_available": has_update,
        "local_ahead": local_ahead,
        "is_git_repo": commit is not None,
    }
