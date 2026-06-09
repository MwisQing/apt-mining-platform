#!/usr/bin/env python3
"""APT Mining Workbench - 一键上传脚本（开发侧）

功能：
1. 自动初始化 git 仓库（从 GitHub 下载的纯净包无 .git）
2. 检查 git 变更
3. 提交代码（排除敏感目录）
4. 推送到远程
5. 创建并推送版本标签
"""

import os
import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)

# 远程仓库地址（从 GitHub 下载时自动配置）
DEFAULT_REMOTE = "https://github.com/MwisQing/apt-mining-platform.git"

# git add 时排除的目录/文件
GIT_EXCLUDE = [
    "data/", "uploads/", "backups/", "releases/",
    "venv/", "node_modules/", "__pycache__/",
    ".gocache/", ".gomodcache/",
    "backend_v2/.gocache/", "backend_v2/.gomodcache/",
    "backend_v2/uploads/",
    ".env", "*.db", "tmp_*.db", "*_regression.db", "uploads-test",
]


def git_exclude_pathspec(pattern: str) -> str:
    normalized = pattern.replace("\\", "/")
    if normalized.endswith("/"):
        return f":(exclude){normalized}**"
    return f":(exclude){normalized}"


def quote_git_arg(arg: str) -> str:
    return '"' + arg.replace('"', '\\"') + '"'


def build_git_add_command() -> str:
    excludes = " ".join(
        quote_git_arg(git_exclude_pathspec(pattern)) for pattern in GIT_EXCLUDE
    )
    return f"git add -A -- . {excludes}"


def print_header():
    print("=" * 40)
    print("APT Mining Workbench - 一键上传")
    print("=" * 40)


def run(cmd: str, capture: bool = False) -> subprocess.CompletedProcess:
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


def is_git_repo() -> bool:
    result = run("git rev-parse --is-inside-work-tree", capture=True)
    return result.returncode == 0


def init_git_repo() -> bool:
    """初始化 git 仓库"""
    print("  未检测到 git 仓库，正在初始化...")
    result = run("git init")
    if result.returncode != 0:
        print("  git init 失败！")
        return False
    print("  git 仓库已初始化。")
    return True


def ensure_remote() -> bool:
    """确保远程仓库已配置"""
    result = run("git remote get-url origin", capture=True)
    if result.returncode == 0:
        print(f"  远程仓库: {result.stdout.strip()}")
        return True

    # 无远程仓库，自动添加默认地址
    print(f"  未配置远程仓库，正在添加默认地址...")
    print(f"  {DEFAULT_REMOTE}")
    result = run(f'git remote add origin {DEFAULT_REMOTE}')
    if result.returncode != 0:
        print("  添加远程仓库失败。")
        return False
    print("  远程仓库已添加。")
    return True


def has_changes() -> bool:
    """检查是否有未提交的变更（包括未跟踪文件）"""
    # 检查 staged + unstaged + untracked
    result = run("git status --porcelain", capture=True)
    return bool(result.stdout.strip())


def show_changes():
    run("git status --short")


def git_add_safe() -> bool:
    """安全地添加文件，排除敏感目录"""
    # Exclude cache/sensitive paths during add so Git does not scan them.
    run(build_git_add_command())

    # 然后移除不应提交的文件
    for pattern in GIT_EXCLUDE:
        run(f"git reset HEAD -- {pattern}")

    return True


def git_commit(msg: str) -> bool:
    """提交代码"""
    result = run(f'git commit -m "{msg}"')
    return result.returncode == 0


def get_current_branch() -> str:
    result = run("git branch --show-current", capture=True)
    branch = result.stdout.strip()
    if not branch:
        # 首次提交可能没有分支名，使用 main
        run("git branch -M main")
        return "main"
    return branch


def git_push() -> bool:
    branch = get_current_branch()
    if not branch:
        print("  错误: 无法获取当前分支名。")
        return False
    # -u 设置上游分支，首次推送需要
    result = run(f"git push -u origin {branch}")
    if result.returncode != 0:
        # 首次推送可能需要 force（远程有历史）
        print("  推送失败，尝试 force push...")
        result = run(f"git push -u origin {branch} --force")
    return result.returncode == 0


def read_version() -> str:
    ver_file = SCRIPT_DIR / "VERSION"
    if ver_file.exists():
        return ver_file.read_text(encoding="utf-8").strip()
    return "未知"


def parse_version(full_ver: str) -> tuple:
    """将 '4.0.1 go重构平台' 拆分为 ('4.0.1', 'go重构平台')"""
    parts = full_ver.split(None, 1)
    ver = parts[0] if parts else "0.0.0"
    desc = parts[1] if len(parts) > 1 else ""
    return ver, desc


def tag_exists(tag: str) -> bool:
    result = run(f'git tag -l "{tag}"', capture=True)
    return bool(result.stdout.strip())


def create_and_push_tag(tag: str, message: str = "") -> bool:
    if message:
        result = run(f'git tag -a "{tag}" -m "{message}"')
    else:
        result = run(f'git tag "{tag}"')
    if result.returncode != 0:
        return False
    result = run("git push origin --tags --force")
    return result.returncode == 0


def main():
    print_header()

    # 检查 git
    if not check_git():
        print("错误: 未检测到 Git，请先安装 Git。")
        input("按任意键继续...")
        sys.exit(1)

    # 检查是否是 git 仓库，不是则初始化
    if not is_git_repo():
        if not init_git_repo():
            input("按任意键继续...")
            sys.exit(1)

    # 确保远程仓库
    print("\n检查远程仓库...")
    if not ensure_remote():
        print("远程仓库配置失败。")
        input("按任意键继续...")
        sys.exit(1)

    # 检查变更
    if not has_changes():
        print("\n没有需要提交的变更。")
        input("按任意键继续...")
        sys.exit(0)

    # 展示变更
    print("\n变更文件:")
    show_changes()
    print()

    # 输入提交说明
    commit_msg = input("请输入提交说明: ").strip()
    if not commit_msg:
        print("提交说明不能为空。")
        input("按任意键继续...")
        sys.exit(1)

    # 添加文件（排除敏感目录）
    print("\n[1/3] 添加文件...")
    git_add_safe()
    print("  完成")

    # 提交
    print("[2/3] 提交代码...")
    if not git_commit(commit_msg):
        print("Git 提交失败！")
        input("按任意键继续...")
        sys.exit(1)
    print("  完成")

    # 推送
    print("[3/3] 推送到远程...")
    if not git_push():
        print("推送失败，请检查远程仓库地址和权限。")
        input("按任意键继续...")
        sys.exit(1)
    print("  完成")

    # 标签
    full_ver = read_version()
    ver, desc = parse_version(full_ver)
    tag = f"v{ver}"
    tag_msg = desc if desc else f"Release v{ver}"
    print(f"\n创建标签 {tag}...")
    if tag_exists(tag):
        print(f"  标签 {tag} 已存在。")
        confirm = input(f"  是否更新到当前提交? [y/N]: ").strip()
        if confirm.lower() == "y":
            run(f'git tag -d "{tag}"')
            if not create_and_push_tag(tag, tag_msg):
                print(f"  标签 {tag} 推送失败！")
                input("按任意键继续...")
                sys.exit(1)
            print(f"  标签 {tag} 已更新。")
        else:
            print(f"  跳过标签更新。")
    else:
        if create_and_push_tag(tag, tag_msg):
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
