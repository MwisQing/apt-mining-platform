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

# 升级时排除的目录和文件
EXCLUDE_DIRS = {
    "data", "uploads", "backups", "venv", "node_modules",
    ".git", ".claude", "_upgrade_tmp", "releases",
}
EXCLUDE_FILE_PATTERNS = {"*.pyc", "tmp_*.db", "*_regression.db"}


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

        # 复制覆盖（排除敏感目录）
        print("  正在覆盖文件...")
        for item in source_dir.iterdir():
            if item.name in EXCLUDE_DIRS:
                continue
            skip = False
            for pat in EXCLUDE_FILE_PATTERNS:
                if fnmatch.fnmatch(item.name, pat):
                    skip = True
                    break
            if skip:
                continue

            dest = SCRIPT_DIR / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
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

    # fetch
    print("  正在获取最新代码...")
    result = run("git fetch origin")
    if result.returncode != 0:
        print("  错误: git fetch 失败！")
        return False

    branch = get_current_branch()
    if not branch:
        print("  错误: 无法获取当前分支名。")
        return False

    # 比较 HEAD vs origin/<branch>
    head = run("git rev-parse HEAD", capture=True).stdout.strip()
    origin = run(f"git rev-parse origin/{branch}", capture=True).stdout.strip()

    if head == origin:
        print("  代码已经是最新的，无需拉取。")
        return True

    print("  检测到新版本，正在拉取...")
    result = run(f"git pull origin {branch}")
    if result.returncode != 0:
        print("  git pull 失败！")
        return False

    print("  代码拉取完成。")
    return True


def install_backend_deps() -> bool:
    """安装后端依赖"""
    activate = SCRIPT_DIR / "venv" / "Scripts" / "activate.bat"
    if not activate.exists():
        print("  venv 不存在，请先执行 install.bat。")
        return False

    venv_python = SCRIPT_DIR / "venv" / "Scripts" / "python.exe"
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
    frontend_pkg = SCRIPT_DIR / "frontend" / "package.json"
    if not frontend_pkg.exists():
        print("  frontend/package.json 不存在，跳过前端构建。")
        return True

    print("  正在构建前端...")
    result = subprocess.run(
        "npm install --silent",
        shell=True,
        cwd=SCRIPT_DIR / "frontend",
        capture_output=True,
    )
    result = subprocess.run(
        "npm run build",
        shell=True,
        cwd=SCRIPT_DIR / "frontend",
    )
    if result.returncode != 0:
        print("  警告: 前端构建失败，请手动处理。")
        return False
    print("  完成")
    return True


def check_git() -> bool:
    result = run("where git", capture=True)
    return result.returncode == 0


def has_git_remote() -> bool:
    result = run("git remote", capture=True)
    return bool(result.stdout.strip())


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
            print("或安装 Git 并配置远程仓库。")
            input("按任意键继续...")
            sys.exit(1)

        if not has_git_remote():
            print()
            print("未找到离线升级包，也未配置 Git 远程仓库。")
            print("请将 apt-mining-v*.zip 放到当前目录后重试，")
            print("或执行: git remote add origin <仓库地址>")
            input("按任意键继续...")
            sys.exit(1)

        if not upgrade_from_git():
            input("按任意键继续...")
            sys.exit(1)

    # [3/5] 安装后端依赖
    print("[3/5] 安装后端依赖...")
    install_backend_deps()

    # [4/5] 构建前端
    print("[4/5] 构建前端...")
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
