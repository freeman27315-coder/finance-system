#!/usr/bin/env python3
"""GPT Dev Agent - Webhook 服务器 (部署在 Mac M4)"""
import hmac
import hashlib
import json
import os
import subprocess
import tempfile
import re
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from openai import OpenAI

app = FastAPI(title="GPT Dev Agent")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
REPO = "freeman27315-coder/finance-system"
REPO_URL = f"https://{GITHUB_TOKEN}@github.com/{REPO}.git"

client = OpenAI(api_key=OPENAI_API_KEY)


def verify_signature(payload: bytes, sig_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def run(cmd: list, cwd: str = None) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def generate_code(issue_title: str, issue_body: str) -> dict:
    """调用 GPT-4o 根据 Issue 生成代码"""
    prompt = f"""你是一名专业的 Python 后端工程师，正在开发一个财务系统。

## 任务
{issue_title}

## 需求详情
{issue_body}

## 要求
1. 使用 Python FastAPI 框架
2. 代码完整可运行，包含所有依赖
3. 严格按照需求中的验收标准实现
4. 代码风格：类型注解、清晰的函数命名
5. 返回 JSON 格式，包含以下字段：
   - files: 文件列表，每项包含 path 和 content
   - summary: 实现说明（中文，200字以内）
   - test_commands: 测试命令列表

只返回 JSON，不要任何其他文字。"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)


def process_issue(issue_number: int, issue_title: str, issue_body: str):
    """在后台处理 Issue：生成代码 → 提交 PR"""
    branch = f"feature/issue-{issue_number}"

    # 标记为 in-progress
    subprocess.run([
        "gh", "issue", "edit", str(issue_number),
        "--repo", REPO,
        "--remove-label", "ready-for-dev",
        "--add-label", "in-progress",
    ], env={**os.environ, "GH_TOKEN": GITHUB_TOKEN})

    with tempfile.TemporaryDirectory() as tmpdir:
        # 克隆仓库
        run(["git", "clone", REPO_URL, tmpdir])
        run(["git", "config", "user.email", "gpt-agent@finance-system.ai"], cwd=tmpdir)
        run(["git", "config", "user.name", "GPT Dev Agent"], cwd=tmpdir)
        run(["git", "checkout", "-b", branch], cwd=tmpdir)

        # GPT 生成代码
        result = generate_code(issue_title, issue_body)

        # 写入文件
        for file_info in result.get("files", []):
            file_path = Path(tmpdir) / file_info["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_info["content"], encoding="utf-8")

        # 提交
        run(["git", "add", "-A"], cwd=tmpdir)
        run(["git", "commit", "-m", f"feat: {issue_title}\n\nCloses #{issue_number}"], cwd=tmpdir)
        run(["git", "push", "origin", branch], cwd=tmpdir)

    # 创建 PR
    pr_body = f"""## 实现说明
{result.get('summary', '')}

## 关联 Issue
Closes #{issue_number}

## 测试命令
```bash
{chr(10).join(result.get('test_commands', ['# 暂无测试命令']))}
```

---
> 由 GPT Dev Agent 自动生成，请 Claude PM 审查"""

    subprocess.run([
        "gh", "pr", "create",
        "--repo", REPO,
        "--title", f"[PR] {issue_title}",
        "--body", pr_body,
        "--base", "main",
        "--head", branch,
        "--label", "in-review",
    ], env={**os.environ, "GH_TOKEN": GITHUB_TOKEN})


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event")
    data = json.loads(payload)

    # 监听 Issue 打上 ready-for-dev 标签
    if event == "issues" and data.get("action") == "labeled":
        label = data["label"]["name"]
        if label == "ready-for-dev":
            issue = data["issue"]
            background_tasks.add_task(
                process_issue,
                issue["number"],
                issue["title"],
                issue["body"] or "",
            )
            return {"status": "processing", "issue": issue["number"]}

    return {"status": "ignored"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "GPT Dev Agent"}
