#!/usr/bin/env python3
"""Claude PM - 创建结构化 GitHub Issue"""
import subprocess
import sys
import json

REPO = "freeman27315-coder/finance-system"

def create_issue(title: str, body: str, priority: str = "P1") -> str:
    priority_map = {"P0": "P0-紧急", "P1": "P1-高优", "P2": "P2-正常", "P3": "P3-低优"}
    label = priority_map.get(priority, "P1-高优")

    result = subprocess.run([
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
        "--label", "ready-for-dev",
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"创建 Issue 失败: {result.stderr}")
    return result.stdout.strip()


def list_issues(label: str = "ready-for-dev") -> list:
    result = subprocess.run([
        "gh", "issue", "list",
        "--repo", REPO,
        "--label", label,
        "--json", "number,title,labels,createdAt",
    ], capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout else []


def review_pr(pr_number: int, approve: bool, comment: str) -> None:
    action = "--approve" if approve else "--request-changes"
    subprocess.run([
        "gh", "pr", "review", str(pr_number),
        "--repo", REPO,
        action,
        "--body", comment,
    ], check=True)


if __name__ == "__main__":
    # 示例：创建一个财务系统 Issue
    url = create_issue(
        title="[FEAT] 用户登录与权限管理模块",
        body="""## 需求描述
实现财务系统的用户认证与基于角色的权限控制。

## 业务背景
财务数据敏感，需要严格控制不同角色（管理员、财务员、审计员）的访问权限。

## 验收标准
- [ ] 支持用户名/密码登录，JWT Token 认证
- [ ] 三种角色：admin / accountant / auditor
- [ ] admin 可管理用户；accountant 可录入账单；auditor 只读
- [ ] 登录失败超过5次锁定账号
- [ ] Token 过期时间 8 小时

## 技术说明
**技术栈：** Python FastAPI + SQLite + bcrypt + JWT
**接口规范：**
- POST /auth/login → {token, role}
- POST /auth/logout
- GET /users (admin only)
- POST /users (admin only)

## 优先级
- [x] P1 - 高优

## 预计工时
4小时""",
        priority="P1"
    )
    print(f"Issue 已创建: {url}")
