#!/usr/bin/env python3
"""APT Mining Workbench - 一键升级脚本（正式侧）

功能：
1. 备份数据库
2. 检测升级方式（离线 ZIP 包优先，回退 Git pull）
3. 安装后端依赖
4. 构建前端
5. 版本确认
"""

import os
import sys
import shutil
import zipfile
import subprocess
import glob
import fnmatch
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
    """备份数据库，返回备份路径"""
    db_path = SCRIPT_DIR / "data" / "workbench.db"
    if not db_path.exists():
        print("  数据库不存在，跳过备份。")
        return ""

    backups_dir = SCRIPT_DIR / "backups"
    backups_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"workbench_{timestamp}.db"

    try:
        shutil.copy2(db_path, backup_path)
        print(f"  已备份: {backup_path}")
        return str(backup_path)
    except Exception as e:
        print(f"  警告: 数据库备份失败！({e})")
        return ""


def _merge_dir(src, dst):
    """Merge src directory into dst, overwriting individual files but preserving
    files that exist only in dst (local files not in the zip)."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in EXCLUDE_DIRS:
            continue
        for pat in EXCLUDE_FILE_PATTERNS:
            if fnmatch.fnmatch(item.name, pat):
                break
        else:
            dest_item = dst / item.name
            if item.is_dir():
                _merge_dir(item, dest_item)
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
    """安装后端依赖"""
    if os.name == "nt":
        activate = SCRIPT_DIR / "venv" / "Scripts" / "activate.bat"
        venv_python = SCRIPT_DIR / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = SCRIPT_DIR / "venv" / "bin" / "python3"

    if not venv_python.exists():
        print("  venv 不存在，请先执行 install.sh 或 install.py。")
        return False

    requirements = SCRIPT_DIR / "requirements.txt"

    print("  正在安装后端依赖...")
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements), "-q"],
        cwd=SCRIPT_DIR,
    )
    if result.returncode != 0:
        print("  警告: 后端依赖安装失败，请手动处理。")
        return False
    print("  完成")
    return True


def build_frontend() -> bool:
    """构建前端"""
    frontend_dir = SCRIPT_DIR / "frontend"
    frontend_pkg = frontend_dir / "package.json"
    dist_file = frontend_dir / "dist" / "index.html"

    # Release package already includes built frontend/dist/, skip build
    if dist_file.exists():
        print("  前端构建产物已存在，跳过 npm install + build。")
        return True

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
    print_header()

    old_ver = read_version()
    print(f"当前版本: {old_ver}")

    # [1/5] 备份数据库
    print()
    print("[1/5] 备份数据库...")
    backup_path = backup_database()

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

    # [5/5] 构建前端
    print("[5/5] 构建前端...")
    build_frontend()

    # [5/5] 版本确认
    print("[5/5] 版本确认...")
    new_ver = read_version()
    print(f"{old_ver} >> {new_ver}")

    print()
    print("=" * 40)
    print("升级完成！请执行 start.bat 启动平台。")
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
