#!/usr/bin/env python3
"""APT Mining Workbench - 一键打包脚本（开发侧）

功能：
1. 读取/更新版本号
2. 构建前端
3. 复制项目文件（排除数据/临时目录）
4. 打包为 releases/ 下的 zip 文件
"""

import fnmatch
import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

# 确保脚本在项目根目录运行
SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)

EXCLUDE_DIRS = {
    "data", "uploads", "backups", "venv", "node_modules",
    ".git", ".claude", "__pycache__", "releases", "_release_tmp",
    "logs","uploads-test",
}
EXCLUDE_FILE_PATTERNS = {"*.pyc", "tmp_*.db", "*_regression.db"}


def print_header():
    print("=" * 40)
    print("APT Mining Workbench - 一键打包")
    print("=" * 40)


def read_version() -> str:
    ver_file = SCRIPT_DIR / "VERSION"
    if ver_file.exists():
        return ver_file.read_text(encoding="utf-8").strip()
    return "未知"


def write_version(ver: str):
    (SCRIPT_DIR / "VERSION").write_text(ver + "\n", encoding="utf-8")


def suggest_version(old_ver: str) -> str:
    """最后一位+1"""
    parts = old_ver.split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            pass
    return old_ver


def copy_ignore_func(_dir, files):
    """shutil.copytree ignore 回调，排除 __pycache__、*.pyc、node_modules"""
    ignored = [f for f in files if fnmatch.fnmatch(f, "*.pyc")]
    if "node_modules" in files:
        ignored.append("node_modules")
    return ignored


def build_frontend() -> bool:
    frontend_pkg = SCRIPT_DIR / "frontend" / "package.json"
    if not frontend_pkg.exists():
        print("  警告: frontend/package.json 不存在，跳过前端构建")
        return True

    print("  正在构建前端...")
    result = subprocess.run(
        "npm run build",
        shell=True,
        cwd=SCRIPT_DIR / "frontend",
    )
    if result.returncode != 0:
        print("  前端构建失败！")
        return False
    print("  完成")
    return True


def copy_project(tmp_dir: Path):
    """复制项目文件到临时目录，排除敏感/临时目录"""
    print("  正在复制文件...")
    src = SCRIPT_DIR
    for item in src.iterdir():
        if item.name in EXCLUDE_DIRS:
            continue
        if item.name.startswith("_release_tmp"):
            continue
        dest = tmp_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=copy_ignore_func)
        else:
            skip = False
            for pat in EXCLUDE_FILE_PATTERNS:
                if fnmatch.fnmatch(item.name, pat):
                    skip = True
                    break
            if not skip:
                shutil.copy2(item, dest)


def create_zip(tmp_dir: Path, version: str) -> Path:
    """创建 zip 压缩包"""
    releases_dir = SCRIPT_DIR / "releases"
    releases_dir.mkdir(exist_ok=True)
    zip_file = releases_dir / f"apt-mining-v{version}.zip"

    if zip_file.exists():
        zip_file.unlink()

    print(f"  正在打包到 {zip_file}...")
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in tmp_dir.rglob("*"):
            if item.is_file():
                arcname = item.relative_to(tmp_dir)
                zf.write(item, arcname)

    return zip_file


def main():
    print_header()

    # 1. 版本号
    old_ver = read_version()
    print(f"当前版本: {old_ver}")
    suggested = suggest_version(old_ver)
    input_ver = input(f"请输入新版本号 [{suggested}]: ").strip()
    ver = input_ver if input_ver else suggested
    write_version(ver)
    print(f"[1/3] 更新版本号... {ver}")

    # 2. 构建前端
    print("[2/3] 构建前端...")
    if not build_frontend():
        input("按任意键继续...")
        sys.exit(1)

    # 3. 复制 + 打包
    print("[3/3] 打包文件...")
    tmp_dir = SCRIPT_DIR / "_release_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    try:
        copy_project(tmp_dir)
        zip_file = create_zip(tmp_dir, ver)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

    print()
    print(f"已打包: {zip_file}")
    print("请将此文件发送给正式环境。")
    print("=" * 40)
    input("按任意键继续...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(0)
