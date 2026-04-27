#!/usr/bin/env python3
"""开发者 GitHub 操作助手

用法：
  python github_helper.py start <issue_number>   # 创建分支，开始开发
  python github_helper.py submit <issue_number>  # 提交 PR，进入审查
  python github_helper.py list                   # 查看待开发的 Issues
"""
import io
import os
import subprocess
import sys

# 强制 stdout/stderr 使用 UTF-8，防止中文显示为 ???
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH = os.environ.get("GH_PATH", "gh")
REPO = "freeman27315-coder/finance-system"
REPO_URL = f"https://{GITHUB_TOKEN}@github.com/{REPO}.git"

# 子进程统一 UTF-8 环境
UTF8_ENV = {
    **os.environ,
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
    "PYTHONIOENCODING": "utf-8",
}

if not GITHUB_TOKEN:
    print("错误: GITHUB_TOKEN 未设置，请检查 .env 并执行 source .env")
    sys.exit(1)


def run(cmd: list, cwd: str = None, check: bool = True) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=UTF8_ENV,
        cwd=cwd,
    )
    if check and result.returncode != 0:
        print(f"错误: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def cmd_start(issue_number: str):
    """拉取最新 main，创建 feature 分支"""
    branch = f"feature/issue-{issue_number}"
    run(["git", "fetch", "origin"])
    run(["git", "checkout", "main"])
    run(["git", "pull", "origin", "main"])
    run(["git", "checkout", "-b", branch])
    print(f"已切换到分支: {branch}")
    print(f"Issue 详情: https://github.com/{REPO}/issues/{issue_number}")


def cmd_submit(issue_number: str):
    """推送当前分支并创建 PR"""
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "main":
        print("错误: 请先切换到 feature 分支再提交")
        sys.exit(1)

    # 获取 Issue 标题
    issue_info = run([
        GH, "issue", "view", issue_number,
        "--repo", REPO,
        "--json", "title,body",
    ])
    import json
    info = json.loads(issue_info)
    title = info["title"]

    # 推送分支
    run(["git", "push", "-u", "origin", branch])

    # 创建 PR
    pr_body = f"""## 关联 Issue
Closes #{issue_number}

## 改动说明
<!-- 简要描述本次实现的内容 -->

## 自测情况
- [ ] 已本地运行验证
- [ ] 满足 Issue 中的验收标准

---
> 请 Claude PM 审查"""

    result = subprocess.run(
        [
            GH, "pr", "create",
            "--repo", REPO,
            "--title", f"[PR] {title}",
            "--body", pr_body,
            "--base", "main",
            "--head", branch,
            "--label", "in-review",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**UTF8_ENV, "GH_TOKEN": GITHUB_TOKEN},
    )
    if result.returncode != 0:
        print(f"创建 PR 失败: {result.stderr.strip()}")
        sys.exit(1)

    pr_url = result.stdout.strip()

    # 更新 Issue 标签
    subprocess.run([
        GH, "issue", "edit", issue_number,
        "--repo", REPO,
        "--remove-label", "in-progress",
        "--add-label", "in-review",
    ], env={**UTF8_ENV, "GH_TOKEN": GITHUB_TOKEN})

    print(f"PR 已创建: {pr_url}")
    print(f"Issue #{issue_number} 已更新为 in-review，等待 Claude PM 审查")


def cmd_list():
    """列出所有待开发的 Issues"""
    result = run([
        GH, "issue", "list",
        "--repo", REPO,
        "--label", "ready-for-dev",
        "--json", "number,title,createdAt",
    ])
    import json
    issues = json.loads(result) if result else []
    if not issues:
        print("暂无待开发任务")
        return
    print(f"\n待开发任务 ({len(issues)} 个):")
    for issue in issues:
        print(f"  #{issue['number']}  {issue['title']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]
    if command == "start" and len(sys.argv) == 3:
        cmd_start(sys.argv[2])
    elif command == "submit" and len(sys.argv) == 3:
        cmd_submit(sys.argv[2])
    elif command == "list":
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)
