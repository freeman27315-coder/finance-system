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

# 默认空：agent 收到事件后只标记 + 写任务文件 + 终端通知，不自动激活任何 CLI
# （适用于开发者用 ChatGPT 网页/桌面版的场景——开发者看到通知后手动让 ChatGPT 读任务文件）
# 如果用 Claude Code 等支持 -p 模式的 CLI，可以填入：
#   claude -p "请认领并完成任务 #{issue_number}：{issue_title}。详情：{issue_url}。{action_hint}"
AGENT_DISPATCH_CMD = os.environ.get("AGENT_DISPATCH_CMD", "")

# 任务文件存放目录（开发者把这个文件丢给 ChatGPT 即可看完整需求）
TASKS_DIR = os.environ.get("TASKS_DIR", os.path.expanduser("~/finance-system-tasks"))
os.makedirs(TASKS_DIR, exist_ok=True)

# macOS 桌面通知（可选，靠 osascript）
DESKTOP_NOTIFY = os.environ.get("DESKTOP_NOTIFY", "1") == "1"

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


def fetch_issue_body(issue_number: int) -> str:
    """通过 gh 拉 Issue 完整正文，写到任务文件给 AI 助手参考"""
    try:
        result = subprocess.run(
            [GH, "issue", "view", str(issue_number), "--repo", REPO, "--json", "title,body,labels"],
            capture_output=True, text=True, encoding="utf-8", env=utf8_env(), timeout=20,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception as exc:
        return f"(获取失败: {exc})"
    return ""


def write_task_file(issue_number: int, issue_title: str, issue_url: str, action_hint: str) -> str:
    """把完整任务写到本地文件，开发者直接丢给 ChatGPT"""
    body_json = fetch_issue_body(issue_number)
    path = os.path.join(TASKS_DIR, f"issue-{issue_number}.md")
    workflow = (
        "## 工作流（请 AI 助手按此操作）\n"
        f"1. 在仓库根目录运行：`python agent/github_helper.py start {issue_number}`（自动创建分支）\n"
        f"2. 按下方需求写代码，遵循已有代码风格\n"
        f"3. 提交：`git add -A && git commit -m \"feat: ...\"`\n"
        f"4. 提交 PR：`python agent/github_helper.py submit {issue_number}`\n"
    )
    content = (
        f"# 任务 #{issue_number}: {issue_title}\n\n"
        f"**链接：** {issue_url}\n\n"
        + (f"**修改提示（来自 review）：**\n{action_hint}\n\n" if action_hint else "")
        + workflow + "\n"
        + "---\n\n## Issue 完整内容（JSON）\n\n```json\n" + body_json + "\n```\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def desktop_notify(title: str, message: str):
    """macOS 桌面通知（也兼容 Windows / Linux 失败时静默）"""
    if not DESKTOP_NOTIFY:
        return
    try:
        if sys.platform == "darwin":
            safe_title = title.replace('"', "'")
            safe_msg = message.replace('"', "'")
            subprocess.Popen(
                ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def dispatch_to_assistant(issue_number: int, issue_title: str, issue_url: str, action_hint: str = ""):
    """事件驱动通知开发者：写任务文件 + 终端高亮 + 桌面通知"""
    task_file = write_task_file(issue_number, issue_title, issue_url, action_hint)

    print("\n" + "🟢" * 30)
    print(f"  [{AGENT_LABEL.upper()}] 新任务 #{issue_number}: {issue_title}")
    print(f"  任务文件: {task_file}")
    print(f"  Issue 链接: {issue_url}")
    if action_hint:
        print(f"  修改提示: {action_hint[:200]}")
    print(f"  → 把上面的任务文件丢给 ChatGPT，让它按工作流完成")
    print("🟢" * 30 + "\n", flush=True)

    desktop_notify(
        f"[{AGENT_LABEL}] 新任务 #{issue_number}",
        issue_title[:120],
    )

    # 可选：如配置了 AGENT_DISPATCH_CMD（如 claude -p）则继续启动 CLI 子进程
    if AGENT_DISPATCH_CMD:
        cmd = AGENT_DISPATCH_CMD.format(
            issue_number=issue_number,
            issue_title=issue_title.replace('"', "'"),
            issue_url=issue_url,
            action_hint=action_hint,
        )
        try:
            subprocess.Popen(
                shlex.split(cmd) if os.name != "nt" else cmd,
                env=utf8_env(),
                stdin=subprocess.DEVNULL,
                shell=os.name == "nt",
            )
            print(f"  已额外启动 CLI: {cmd[:80]}...", flush=True)
        except Exception as exc:
            print(f"  ⚠️  CLI 启动失败（不影响通知）：{exc}", flush=True)


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
