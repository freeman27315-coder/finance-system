#!/usr/bin/env python3
"""Dev Agent Webhook 服务器（事件驱动）

职责：监听 GitHub Webhook，收到任务事件后立即激活本机 AI 编程助手开干。
不再依赖任何轮询，所有动作由 GitHub 事件驱动。

事件 → 动作映射：
- issues.labeled (ready-for-dev + 本 agent label) → 标 in-progress + 启动助手开发
- pull_request_review.submitted (changes_requested) → 标 needs-revision + 启动助手修改
- issue_comment.created (PR 上的评论) → 转发给助手参考

环境变量：
  GITHUB_TOKEN       - 必填
  WEBHOOK_SECRET     - 必填
  AGENT_LABEL        - 必填，backend 或 frontend
  GH_PATH            - 可选，gh 可执行文件路径
  AGENT_DISPATCH_CMD - 可选，激活 AI 助手的命令模板。默认调 claude -p。
                       可用占位符：{issue_number} {issue_title} {issue_url} {action_hint}
"""
import hmac
import hashlib
import json
import os
import shlex
import subprocess
import sys
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks

app = FastAPI(title="Dev Agent")

# UTF-8 locale 兜底
os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
AGENT_LABEL = os.environ.get("AGENT_LABEL", "")
GH = os.environ.get("GH_PATH", "gh")
REPO = "freeman27315-coder/finance-system"

# 默认用 claude CLI 激活助手；用户可改成 codex/cursor 等其他 CLI
DEFAULT_DISPATCH_CMD = (
    'claude -p "请认领并完成任务 #{issue_number}：{issue_title}。'
    '详情：{issue_url}。{action_hint}'
    '工作流：1) python github_helper.py start {issue_number}  '
    '2) 阅读 Issue 写代码  3) python github_helper.py submit {issue_number}"'
)
AGENT_DISPATCH_CMD = os.environ.get("AGENT_DISPATCH_CMD", DEFAULT_DISPATCH_CMD)

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN 未设置")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET 未设置")
if not AGENT_LABEL:
    raise RuntimeError("AGENT_LABEL 未设置（backend 或 frontend）")


def verify_signature(payload: bytes, sig_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def get_issue_labels(issue: dict) -> list[str]:
    return [lbl["name"] for lbl in issue.get("labels", [])]


def utf8_env() -> dict:
    return {
        **os.environ,
        "GH_TOKEN": GITHUB_TOKEN,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def edit_issue_label(issue_number: int, remove: Optional[str], add: str):
    args = [GH, "issue", "edit", str(issue_number), "--repo", REPO, "--add-label", add]
    if remove:
        args += ["--remove-label", remove]
    subprocess.run(args, env=utf8_env())


def dispatch_to_assistant(issue_number: int, issue_title: str, issue_url: str, action_hint: str = ""):
    """Fire-and-forget 启动 AI 助手子进程"""
    cmd = AGENT_DISPATCH_CMD.format(
        issue_number=issue_number,
        issue_title=issue_title.replace('"', "'"),
        issue_url=issue_url,
        action_hint=action_hint,
    )
    print("\n" + "=" * 60)
    print(f"  [{AGENT_LABEL.upper()}] 事件触发任务 #{issue_number}: {issue_title}")
    print(f"  详情: {issue_url}")
    print(f"  激活命令: {cmd[:120]}...")
    print("=" * 60 + "\n")
    # 后台启动，不等待结果（助手会自己提交 PR）
    try:
        subprocess.Popen(
            shlex.split(cmd) if os.name != "nt" else cmd,
            env=utf8_env(),
            stdin=subprocess.DEVNULL,
            shell=os.name == "nt",
        )
    except Exception as exc:
        print(f"⚠️  启动助手失败（可手动认领 #{issue_number}）：{exc}", flush=True)


def handle_new_task(issue_number: int, issue_title: str, issue_url: str):
    edit_issue_label(issue_number, "ready-for-dev", "in-progress")
    dispatch_to_assistant(issue_number, issue_title, issue_url, "")


def handle_revision(issue_number: int, issue_title: str, issue_url: str, review_body: str):
    edit_issue_label(issue_number, "in-review", "needs-revision")
    hint = f"PR 被打回修改，原因：{review_body[:300]}。请阅读 review 后修复并重新提交。"
    dispatch_to_assistant(issue_number, issue_title, issue_url, hint)


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    data = json.loads(payload.decode("utf-8"))

    # 1. 新任务：ready-for-dev + 本 agent label
    if event == "issues" and data.get("action") == "labeled":
        if data["label"]["name"] == "ready-for-dev":
            issue = data["issue"]
            labels = get_issue_labels(issue)
            if AGENT_LABEL in labels:
                background_tasks.add_task(
                    handle_new_task,
                    issue["number"],
                    issue["title"],
                    issue["html_url"],
                )
                return {"status": "dispatched", "issue": issue["number"], "agent": AGENT_LABEL}
            return {"status": "ignored", "reason": f"not labeled '{AGENT_LABEL}'"}

    # 2. PR 被打回修改
    if event == "pull_request_review" and data.get("action") == "submitted":
        review = data.get("review", {})
        if review.get("state") == "changes_requested":
            pr = data["pull_request"]
            labels = [l["name"] for l in pr.get("labels", [])]
            if AGENT_LABEL in labels:
                # PR 关联的 Issue 编号 = 分支名末段或 body 里的 Closes #N
                import re
                m = re.search(r"Closes\s+#(\d+)", pr.get("body") or "", re.IGNORECASE)
                issue_num = int(m.group(1)) if m else pr["number"]
                background_tasks.add_task(
                    handle_revision,
                    issue_num,
                    pr["title"],
                    pr["html_url"],
                    review.get("body") or "",
                )
                return {"status": "revision-dispatched", "pr": pr["number"]}

    return {"status": "ignored", "event": event}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_LABEL or "Dev Agent"}
