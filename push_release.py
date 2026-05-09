#!/usr/bin/env python3
"""APT Mining Workbench - 一键上传脚本（开发侧）

功能：
1. 检查 git 变更
2. 提交代码
3. 推送到远程
4. 创建并推送版本标签
"""

import os
import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)


def print_header():
    print("=" * 40)
    print("APT Mining Workbench - 一键上传")
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


def check_git() -> bool:
    result = run("where git", capture=True)
    return result.returncode == 0


def ensure_remote() -> bool:
    result = run("git remote get-url origin", capture=True)
    if result.returncode == 0:
        print(f"  远程仓库: {result.stdout.strip()}")
        return True
    print("  未配置远程仓库，正在添加...")
    result = run('git remote add origin https://github.com/MwisQing/apt-mining-platform.git')
    if result.returncode != 0:
        print("  添加远程仓库失败。")
        return False
    print("  远程仓库已添加。")
    return True


def has_changes() -> bool:
    result = run("git status --short", capture=True)
    return bool(result.stdout.strip())


def show_changes():
    run("git status --short")


def git_add_commit(msg: str) -> bool:
    run("git add -A")
    result = run(f'git commit -m "{msg}"')
    return result.returncode == 0


def get_current_branch() -> str:
    result = run("git branch --show-current", capture=True)
    return result.stdout.strip()


def git_push() -> bool:
    branch = get_current_branch()
    if not branch:
        print("  错误: 无法获取当前分支名。")
        return False
    result = run(f"git push origin {branch}")
    return result.returncode == 0


def read_version() -> str:
    ver_file = SCRIPT_DIR / "VERSION"
    if ver_file.exists():
        return ver_file.read_text(encoding="utf-8").strip()
    return "未知"


def tag_exists(tag: str) -> bool:
    result = run(f'git tag -l "{tag}"', capture=True)
    return bool(result.stdout.strip())


def create_and_push_tag(tag: str) -> bool:
    run(f"git tag {tag}")
    result = run("git push --tags")
    return result.returncode == 0


def main():
    print_header()

    # 检查 git
    if not check_git():
        print("错误: 未检测到 Git，请先安装 Git。")
        input("按任意键继续...")
        sys.exit(1)

    # 检查变更
    if not has_changes():
        print("没有需要提交的变更。")
        input("按任意键继续...")
        sys.exit(0)

    # 展示变更
    print("变更文件:")
    show_changes()
    print()

    # 输入提交说明
    commit_msg = input("请输入提交说明: ").strip()
    if not commit_msg:
        print("提交说明不能为空。")
        input("按任意键继续...")
        sys.exit(1)

    # 提交
    print("[1/3] 提交代码...")
    if not git_add_commit(commit_msg):
        print("Git 提交失败！")
        input("按任意键继续...")
        sys.exit(1)
    print("  完成")

    # 确保远程仓库
    print("\n检查远程仓库...")
    if not ensure_remote():
        print("远程仓库配置失败。")
        input("按任意键继续...")
        sys.exit(1)

    # 推送
    print("[2/3] 推送到远程...")
    if not git_push():
        print("推送失败，请检查远程仓库。")
        input("按任意键继续...")
        sys.exit(1)
    print("  完成")

    # 标签
    ver = read_version()
    tag = f"v{ver}"
    print(f"[3/3] 创建标签 {tag}...")
    if tag_exists(tag):
        print(f"  标签 {tag} 已存在，跳过推送")
    else:
        if create_and_push_tag(tag):
            print(f"  标签 {tag} 推送成功。")
        else:
            print(f"  标签 {tag} 推送失败！")

    print()
    print("代码已推送，正式环境可执行 upgrade.py 拉取更新。")
    print("=" * 40)
    input("按任意键继续...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(0)
