#!/usr/bin/env python3
"""Dev Agent Webhook 服务器

职责：监听 GitHub Webhook，收到 ready-for-dev 事件后：
1. 检查 Issue 是否包含本 Agent 负责的标签（AGENT_LABEL）
2. 将 Issue 标记为 in-progress
3. 在终端打印任务详情，提示开发者认领

环境变量：
  GITHUB_TOKEN   - 必填
  WEBHOOK_SECRET - 必填
  AGENT_LABEL    - 必填，此 Agent 负责的任务类型，如 backend 或 frontend
  GH_PATH        - 可选，gh 可执行文件完整路径，默认 "gh"
"""
import hmac
import hashlib
import json
import os
import subprocess

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks

app = FastAPI(title="Dev Agent")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
AGENT_LABEL = os.environ.get("AGENT_LABEL", "")
GH = os.environ.get("GH_PATH", "gh")
REPO = "freeman27315-coder/finance-system"

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN 未设置，请检查 .env 文件")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET 未设置，请检查 .env 文件")
if not AGENT_LABEL:
    raise RuntimeError("AGENT_LABEL 未设置，请在 .env 中设置 backend 或 frontend")


def verify_signature(payload: bytes, sig_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def get_issue_labels(issue: dict) -> list[str]:
    return [lbl["name"] for lbl in issue.get("labels", [])]


def mark_in_progress(issue_number: int, issue_title: str, issue_url: str):
    """将 Issue 标记为 in-progress，并在终端输出任务提示"""
    subprocess.run(
        [
            GH, "issue", "edit", str(issue_number),
            "--repo", REPO,
            "--remove-label", "ready-for-dev",
            "--add-label", "in-progress",
        ],
        env={**os.environ, "GH_TOKEN": GITHUB_TOKEN},
    )
    print("\n" + "=" * 60)
    print(f"  [{AGENT_LABEL.upper()}] 新任务 #{issue_number}: {issue_title}")
    print(f"  查看详情: {issue_url}")
    print(f"  分支命名: feature/issue-{issue_number}")
    print("  完成后运行: python github_helper.py submit " + str(issue_number))
    print("=" * 60 + "\n")


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event")
    data = json.loads(payload)

    if event == "issues" and data.get("action") == "labeled":
        if data["label"]["name"] == "ready-for-dev":
            issue = data["issue"]
            labels = get_issue_labels(issue)
            # 只处理带有本 Agent 负责标签的 Issue
            if AGENT_LABEL in labels:
                background_tasks.add_task(
                    mark_in_progress,
                    issue["number"],
                    issue["title"],
                    issue["html_url"],
                )
                return {"status": "acknowledged", "issue": issue["number"], "agent": AGENT_LABEL}
            return {"status": "ignored", "reason": f"not labeled '{AGENT_LABEL}'"}

    return {"status": "ignored"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_LABEL or "Dev Agent"}
