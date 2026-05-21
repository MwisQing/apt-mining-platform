#!/usr/bin/env python3
"""APT Mining Workbench - 一键升级脚本（正式侧）

功能：
1. 检测升级方式（离线 ZIP 包优先，回退 Git pull）
2. 下载 Go 模块依赖
3. 编译 Go 后端
4. 构建前端
5. 版本确认

可选参数：
  --backup   升级前备份数据库（默认不备份）
"""

import os
import sys
import shutil
import zipfile
import subprocess
import glob
import fnmatch
import argparse
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)

# 远程仓库地址（从 GitHub 下载时自动配置）
DEFAULT_REMOTE = "https://github.com/MwisQing/apt-mining-platform.git"

# 升级时排除的目录和文件
EXCLUDE_DIRS = {
    "data", "uploads", "backups", "venv", "node_modules",
    ".git", ".claude", "_upgrade_tmp", "releases",
}
EXCLUDE_FILE_PATTERNS = {"*.pyc", "tmp_*.db", "*_regression.db"}


IS_LINUX = os.name != "nt"


def load_dotenv():
    """Load .env file into os.environ (silently skip if missing)."""
    env_file = SCRIPT_DIR / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ.setdefault(key, value)


def db_env() -> tuple:
    """Return (user, password) for production database from .env."""
    load_dotenv()
    return (
        os.environ.get("APT_DB_USER_PROD", "apt_prod"),
        os.environ.get("APT_DB_PASSWORD_PROD", ""),
    )


def go_env(go_dir: Path) -> dict:
    """Keep Go build cache inside the repo to avoid host cache permission issues."""
    env = os.environ.copy()
    cache_dir = go_dir / ".gocache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    env.setdefault("GOCACHE", str(cache_dir))
    return env


def print_header():
    print("=" * 40)
    print("APT Mining Workbench - 一键升级")
    print("=" * 40)


def run(cmd: str, check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    """运行 shell 命令"""
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=capture,
        text=True,
        cwd=SCRIPT_DIR,
    )


def read_version() -> str:
    ver_file = SCRIPT_DIR / "VERSION"
    if ver_file.exists():
        return ver_file.read_text(encoding="utf-8").strip()
    return "未知"


def backup_database() -> str:
    """备份 PostgreSQL 数据库，返回备份路径"""
    backups_dir = SCRIPT_DIR / "backups"
    backups_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"apt_mining_prod_{timestamp}.sql"

    pg_dump = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" if os.name == "nt" else "pg_dump"
    db_user, db_pass = db_env()
    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass

    try:
        result = subprocess.run(
            [pg_dump, "-h", "127.0.0.1", "-U", db_user,
             "-d", "apt_mining_prod", "-f", str(backup_path)],
            env=env, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            size = os.path.getsize(backup_path) / 1024
            print(f"  已备份: {backup_path} ({size:.0f} KB)")
            return str(backup_path)
        else:
            print(f"  警告: 数据库备份失败！({result.stderr.strip()})")
            return ""
    except Exception as e:
        print(f"  警告: 数据库备份失败！({e})")
        return ""


def _merge_dir(src, dst, skip_version=False):
    """Merge src directory into dst, overwriting individual files but preserving
    files that exist only in dst (local files not in the zip).
    skip_version=True 时排除子目录中的 VERSION 文件（统一使用根目录的 VERSION）。"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in EXCLUDE_DIRS:
            continue
        if skip_version and item.name == "VERSION":
            continue
        for pat in EXCLUDE_FILE_PATTERNS:
            if fnmatch.fnmatch(item.name, pat):
                break
        else:
            dest_item = dst / item.name
            if item.is_dir():
                _merge_dir(item, dest_item, skip_version=True)
            else:
                shutil.copy2(item, dest_item)


def upgrade_from_zip(zip_file: Path) -> bool:
    """从离线 ZIP 包升级"""
    print("离线包模式")
    print(f"找到离线包: {zip_file}")
    print("正在解压并升级...")

    tmp_dir = SCRIPT_DIR / "_upgrade_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    try:
        # 解压
        print("  正在解压...")
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(tmp_dir)

        # 检查嵌套目录
        source_dir = tmp_dir
        for item in tmp_dir.iterdir():
            if item.is_dir() and (item / "VERSION").exists():
                source_dir = item
                break

        # 复制覆盖（排除敏感目录）——文件级覆盖，不替换整个目录
        print("  正在覆盖文件...")
        for item in source_dir.iterdir():
            if item.name in EXCLUDE_DIRS:
                continue
            for pat in EXCLUDE_FILE_PATTERNS:
                if fnmatch.fnmatch(item.name, pat):
                    break
            else:
                dest = SCRIPT_DIR / item.name
                if item.is_dir():
                    # 目录合并：逐个文件覆盖，保留本地额外文件
                    _merge_dir(item, dest)
                else:
                    shutil.copy2(item, dest)

        # 移动已使用的 zip 到 releases
        releases_dir = SCRIPT_DIR / "releases"
        releases_dir.mkdir(exist_ok=True)
        shutil.move(str(zip_file), str(releases_dir / zip_file.name))

        print("离线包升级完成。")
        return True

    except Exception as e:
        print(f"升级失败: {e}")
        return False
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)


def get_current_branch() -> str:
    result = run("git branch --show-current", capture=True)
    return result.stdout.strip()


def upgrade_from_git() -> bool:
    """从 Git 远程仓库升级"""
    print("Git 模式")

    # 如果本地有未跟踪文件，先提交（避免 pull 冲突）
    status = run("git status --porcelain", capture=True)
    if status.stdout.strip():
        print("  检测到本地文件，正在暂存...")
        run("git add -A")
        run('git commit -m "local files before upgrade" --allow-empty')
        print("  本地文件已暂存。")

    # fetch
    print("  正在获取最新代码...")
    result = run("git fetch origin")
    if result.returncode != 0:
        print("  错误: git fetch 失败！")
        return False

    branch = get_current_branch()
    if not branch:
        # 首次提交没有分支，尝试使用 main
        run("git branch -M main")
        branch = "main"

    # 比较 HEAD vs origin/<branch>
    head_result = run("git rev-parse HEAD", capture=True)
    origin_result = run(f"git rev-parse origin/{branch}", capture=True)

    # 如果没有提交过，HEAD 不存在
    if head_result.returncode != 0:
        print("  首次拉取，正在合并远程代码...")
        result = run(f"git pull origin {branch} --allow-unrelated-histories")
        if result.returncode != 0:
            # 合并冲突，强制使用远程版本
            print("  检测到冲突，使用远程版本覆盖...")
            run(f"git checkout origin/{branch} -- .")
            run(f"git pull origin {branch} --allow-unrelated-histories --no-edit")
        print("  代码拉取完成。")
        return True

    head = head_result.stdout.strip()
    origin = origin_result.stdout.strip()

    if head == origin:
        print("  代码已经是最新的，无需拉取。")
        return True

    print("  检测到新版本，正在拉取...")
    result = run(f"git pull origin {branch}")
    if result.returncode != 0:
        # pull 失败，尝试强制覆盖
        print("  合并冲突，使用远程版本覆盖...")
        run(f"git fetch origin")
        run(f"git reset --hard origin/{branch}")
        print("  代码已强制更新。")
        return True

    print("  代码拉取完成。")
    return True


def install_backend_deps() -> bool:
    """安装 Go 后端依赖（go mod download）"""
    go_dir = SCRIPT_DIR / "backend_v2"
    if not (go_dir / "go.mod").exists():
        print("  backend_v2/go.mod 不存在，跳过依赖安装。")
        return True
    env = go_env(go_dir)

    print("  正在下载 Go 依赖...")
    result = subprocess.run(
        ["go", "mod", "download"],
        cwd=str(go_dir), capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"  [WARN] go mod download: {result.stderr.strip()}")
        return True  # 不阻断升级
    print("  完成")
    return True


def build_frontend() -> bool:
    """构建前端"""
    frontend_dir = SCRIPT_DIR / "frontend"
    frontend_pkg = frontend_dir / "package.json"

    if not frontend_pkg.exists():
        print("  frontend/package.json 不存在，跳过前端构建。")
        return True

    print("  正在构建前端...")
    result = subprocess.run(
        "npm install --silent",
        shell=True,
        cwd=str(frontend_dir),
        capture_output=True,
    )
    result = subprocess.run(
        "npm run build",
        shell=True,
        cwd=str(frontend_dir),
    )
    if result.returncode != 0:
        print("  警告: 前端构建失败，请手动处理。")
        return False
    print("  完成")
    return True


def check_go() -> bool:
    """Check if Go is installed."""
    cmd = "where go" if os.name == "nt" else "command -v go"
    result = run(cmd, capture=True)
    return result.returncode == 0


def build_go_backend() -> bool:
    """Build Go backend binary after code update."""
    go_dir = SCRIPT_DIR / "backend_v2"
    if not (go_dir / "go.mod").exists():
        print("  backend_v2/go.mod 不存在，跳过 Go 构建。")
        return True
    env = go_env(go_dir)

    if not check_go():
        print("  [WARN] Go 未安装。可在安装 Go 后执行 python start.py 触发自动编译。")
        print("  如需预编译，请安装 Go 后手动执行: cd backend_v2 && go build -o apt-mining.exe .")
        return True

    print("  正在编译 Go 后端...")

    # Download dependencies
    result = subprocess.run(
        ["go", "mod", "download"],
        cwd=str(go_dir), env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("  [WARN] go mod download 失败，将重试。")

    # Build for current platform
    is_windows = os.name == "nt"
    go_exe = go_dir / ("apt-mining.exe" if is_windows else "apt-mining")

    if go_exe.exists():
        go_exe.unlink()

    result = subprocess.run(
        ["go", "build", "-o", str(go_exe), "."],
        cwd=str(go_dir), env=env,
    )
    if result.returncode != 0:
        print("  [WARN] Go 编译失败。安装 Go 后可改用 python start.py 重新触发编译。")
        return True

    print(f"  Go 二进制: {go_exe}")
    return True


def check_git() -> bool:
    cmd = "where git" if os.name == "nt" else "command -v git"
    result = run(cmd, capture=True)
    return result.returncode == 0


def has_git_remote() -> bool:
    result = run("git remote", capture=True)
    return bool(result.stdout.strip())


def ensure_git_remote() -> bool:
    """确保 git 远程仓库已配置，没有则自动添加"""
    if has_git_remote():
        result = run("git remote get-url origin", capture=True)
        print(f"  远程仓库: {result.stdout.strip()}")
        return True

    print(f"  未配置远程仓库，正在自动添加...")
    print(f"  {DEFAULT_REMOTE}")
    result = run(f"git remote add origin {DEFAULT_REMOTE}")
    if result.returncode != 0:
        print("  添加远程仓库失败。")
        return False
    print("  远程仓库已添加。")
    return True


def init_git_if_needed() -> bool:
    """如果不是 git 仓库则初始化"""
    result = run("git rev-parse --is-inside-work-tree", capture=True)
    if result.returncode == 0:
        return True

    print("  未检测到 git 仓库，正在初始化...")
    result = run("git init")
    if result.returncode != 0:
        print("  git init 失败！")
        return False
    print("  git 仓库已初始化。")
    return True


def fix_permissions():
    """On Linux/macOS, ensure scripts are executable after code update."""
    if os.name == "nt":
        return True  # Windows doesn't need chmod
    scripts = [
        "start.py", "stop.py", "install.py", "upgrade.py",
        "pack_release.py", "push_release.py",
        "start.sh", "stop.sh", "install.sh",
    ]
    for name in scripts:
        p = SCRIPT_DIR / name
        if p.exists():
            try:
                os.chmod(p, p.stat().st_mode | 0o755)
            except Exception:
                pass
    return True


def main():
    parser = argparse.ArgumentParser(description='APT Mining Workbench - 一键升级')
    parser.add_argument('--backup', action='store_true', help='升级前备份数据库（默认不备份）')
    args = parser.parse_args()

    print_header()

    old_ver = read_version()
    print(f"当前版本: {old_ver}")

    # [1/5] 备份数据库（可选）
    print()
    print(f"[1/5] 数据库备份: {'开启' if args.backup else '跳过'}")
    backup_path = ""
    if args.backup:
        backup_path = backup_database()
    else:
        print("  如需备份，请使用 python upgrade.py --backup")

    # [2/5] 检测升级方式
    print("[2/5] 检测升级方式...")

    # 优先检查 ZIP 包
    zip_files = sorted(SCRIPT_DIR.glob("apt-mining-v*.zip"))
    if zip_files:
        zip_file = zip_files[-1]  # 取最新的
        if not upgrade_from_zip(zip_file):
            input("按任意键继续...")
            sys.exit(1)
    else:
        # 没有 zip，尝试 git
        if not check_git():
            print()
            print("未找到离线升级包，也未检测到 Git。")
            print("请将 apt-mining-v*.zip 放到当前目录后重试，")
            print("或安装 Git（https://git-scm.com/）。")
            input("按任意键继续...")
            sys.exit(1)

        # 自动初始化 git 仓库（如果需要）
        if not init_git_if_needed():
            input("按任意键继续...")
            sys.exit(1)

        # 自动配置远程仓库（如果需要）
        if not ensure_git_remote():
            input("按任意键继续...")
            sys.exit(1)

        if not upgrade_from_git():
            input("按任意键继续...")
            sys.exit(1)

    # [3/5] 修复脚本执行权限（Linux/macOS）
    print("[3/5] 修复脚本执行权限...")
    fix_permissions()

    # [4/5] 安装后端依赖
    print("[4/5] 安装后端依赖...")
    install_backend_deps()

    # [4.5/5] 编译 Go 后端
    print("[4.5/5] 编译 Go 后端...")
    build_go_backend()

    # [5/5] 构建前端
    print("[5/5] 构建前端...")
    build_frontend()

    # 版本确认
    new_ver = read_version()
    print()
    print(f"{old_ver} >> {new_ver}")

    print()
    print("=" * 40)
    print("升级完成！请执行 startGo.bat 或 python start.py 启动平台。")
    if backup_path:
        print(f"数据库已备份到备份文件: {backup_path}")
    print("=" * 40)
    input("按任意键继续...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(0)
