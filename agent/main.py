#!/usr/bin/env python3
"""Dev Agent Webhook 服务器 (部署在 Mac M4)

职责：监听 GitHub Webhook，收到 ready-for-dev 事件后：
1. 将 Issue 标记为 in-progress
2. 在终端打印任务详情，提示开发者认领
开发者自行阅读 Issue、写代码，然后用 github_helper.py 提交 PR。
"""
import hmac
import hashlib
import json
import os
import subprocess

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks

app = FastAPI(title="Dev Agent")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
REPO = "freeman27315-coder/finance-system"


def verify_signature(payload: bytes, sig_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def mark_in_progress(issue_number: int, issue_title: str, issue_url: str):
    """将 Issue 标记为 in-progress，并在终端输出任务提示"""
    subprocess.run(
        [
            "gh", "issue", "edit", str(issue_number),
            "--repo", REPO,
            "--remove-label", "ready-for-dev",
            "--add-label", "in-progress",
        ],
        env={**os.environ, "GH_TOKEN": GITHUB_TOKEN},
    )
    print("\n" + "=" * 60)
    print(f"  新任务 #{issue_number}: {issue_title}")
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
            background_tasks.add_task(
                mark_in_progress,
                issue["number"],
                issue["title"],
                issue["html_url"],
            )
            return {"status": "acknowledged", "issue": issue["number"]}

    return {"status": "ignored"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Dev Agent"}
