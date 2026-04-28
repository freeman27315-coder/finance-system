#!/usr/bin/env python3
"""Claude PM Discord Bot

功能：
1. @ 机器人 → Claude 回复（带项目上下文）
2. /status     查看所有 PR/Issue 状态
3. /review N   审查 PR #N
4. /dispatch backend|frontend "标题" "需求" 直接派发任务

LLM 后端两种模式：
- LLM_BACKEND=cli      调用 `claude -p` 子进程（用 Claude Max 订阅额度，零 API 费）
- LLM_BACKEND=api      调用 Anthropic API（需 ANTHROPIC_API_KEY，按量计费）
"""
import os
import asyncio
import hmac
import hashlib
import json
import subprocess

import discord
from discord import app_commands
from aiohttp import web
import httpx

# ===== 配置 =====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("GITHUB_REPO", "freeman27315-coder/finance-system")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
LLM_BACKEND = os.environ.get("LLM_BACKEND", "cli").lower()
CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PM_REPORT_WEBHOOK = os.environ.get("PM_REPORT_WEBHOOK", "")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8081"))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

gh = httpx.AsyncClient(
    base_url="https://api.github.com",
    headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
    timeout=30,
)

if LLM_BACKEND == "api":
    from anthropic import Anthropic
    claude_api = Anthropic(api_key=ANTHROPIC_API_KEY)


SYSTEM_PROMPT = f"""你是 Claude PM，负责 GitHub 仓库 {REPO} 的 AI 团队管理。

团队成员：
- 考尔（backend）：在 Mac 上写 Python FastAPI 后端
- 壮壮（frontend）：在另一台机器上写 Next.js 前端
- 你（Claude PM）：在 Windows 上拆需求、审查代码、合并 PR、向用户汇报

工作流：
- 用户提需求 → 你创建带 backend/frontend 标签的 Issue
- 标签触发 Webhook 推到对应开发者
- 开发者写完提 PR → 你审查 → 合并并向用户汇报

回答风格：简洁、中文、有数据支撑。"""


# ===== LLM 调用统一接口 =====
async def ask_llm(user_text: str, system_extra: str = "") -> str:
    full_system = SYSTEM_PROMPT + ("\n\n" + system_extra if system_extra else "")

    if LLM_BACKEND == "api":
        # API 模式
        msg = claude_api.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=full_system,
            messages=[{"role": "user", "content": user_text}],
        )
        return msg.content[0].text

    # CLI 模式：用 claude -p 子进程，使用本机 Claude Max 鉴权
    # 通过 stdin 传 prompt 避免命令行长度限制和 Windows 转义问题
    full_prompt = f"{full_system}\n\n用户问题：{user_text}"
    # Windows 上 claude 是 .cmd 脚本，必须走 shell；同时用 stdin 喂 prompt
    proc = await asyncio.create_subprocess_shell(
        f'"{CLAUDE_CLI}" -p',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=full_prompt.encode("utf-8"))
    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        return f"CLI 调用失败 (code {proc.returncode})：{err}"
    return stdout.decode("utf-8", errors="replace").strip()


# ===== GitHub 帮助函数 =====
async def gh_get(path: str):
    r = await gh.get(path)
    r.raise_for_status()
    return r.json()


async def gh_post(path: str, data: dict):
    r = await gh.post(path, json=data)
    r.raise_for_status()
    return r.json()


async def get_repo_status_summary() -> str:
    prs = await gh_get(f"/repos/{REPO}/pulls?state=open")
    issues_raw = await gh_get(f"/repos/{REPO}/issues?state=open")
    issues = [i for i in issues_raw if "pull_request" not in i]

    lines = [f"**仓库：** {REPO}\n"]
    lines.append(f"**开放 PR ({len(prs)})：**")
    for p in prs[:10]:
        labels = ", ".join(l["name"] for l in p.get("labels", []))
        lines.append(f"  • #{p['number']} {p['title']}  [{labels}]")
    lines.append(f"\n**开放 Issue ({len(issues)})：**")
    for i in issues[:15]:
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        lines.append(f"  • #{i['number']} {i['title']}  [{labels}]")
    return "\n".join(lines)


async def send_chunked(target, text: str):
    for i in range(0, len(text), 1900):
        await target.send(text[i:i+1900])


# ===== Slash 命令 =====
@tree.command(name="status", description="查看仓库当前 PR / Issue 状态")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        text = await get_repo_status_summary()
        await interaction.followup.send(text[:1900])
    except Exception as exc:
        await interaction.followup.send(f"查询失败：{exc}")


@tree.command(name="review", description="让 Claude 审查指定 PR")
@app_commands.describe(pr_number="PR 编号")
async def review_cmd(interaction: discord.Interaction, pr_number: int):
    await interaction.response.defer()
    try:
        pr = await gh_get(f"/repos/{REPO}/pulls/{pr_number}")
        files = await gh_get(f"/repos/{REPO}/pulls/{pr_number}/files")
        file_summary = "\n".join(
            f"  {f['status']} {f['filename']} (+{f['additions']} -{f['deletions']})"
            for f in files[:30]
        )
        prompt = f"""请审查这个 PR：
标题：{pr['title']}
分支：{pr['head']['ref']}
正文：{(pr.get('body') or '')[:1000]}
变更文件：
{file_summary}

请给出 200 字以内的中文审查结论：通过 / 打回，关键问题。"""
        text = await ask_llm(prompt)
        await send_chunked(interaction.followup, f"**PR #{pr_number} 审查结果**\n\n{text}")
    except Exception as exc:
        await interaction.followup.send(f"审查失败：{exc}")


@tree.command(name="dispatch", description="派发新任务给指定开发者")
@app_commands.describe(target="backend 或 frontend", title="任务标题", body="任务详情")
@app_commands.choices(target=[
    app_commands.Choice(name="backend (考尔)", value="backend"),
    app_commands.Choice(name="frontend (壮壮)", value="frontend"),
])
async def dispatch_cmd(
    interaction: discord.Interaction,
    target: app_commands.Choice[str],
    title: str,
    body: str,
):
    await interaction.response.defer()
    try:
        result = await gh_post(f"/repos/{REPO}/issues", {
            "title": title,
            "labels": ["ready-for-dev", target.value],
            "body": body,
        })
        await interaction.followup.send(
            f"✅ 任务已派发给 **{target.name}**\nIssue #{result['number']}: {result['html_url']}"
        )
    except Exception as exc:
        await interaction.followup.send(f"派发失败：{exc}")


# ===== @ 提问 =====
@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or not client.user:
        return
    if client.user not in message.mentions:
        return

    content = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    if not content:
        return

    async with message.channel.typing():
        try:
            status = await get_repo_status_summary()
            answer = await ask_llm(content, system_extra=f"当前仓库快照：\n{status}")
            await send_chunked(message.channel, answer)
        except Exception as exc:
            await message.channel.send(f"处理失败：{exc}")


@client.event
async def on_ready():
    print(f"已登录: {client.user}  (LLM 后端: {LLM_BACKEND})")
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"Slash 命令已同步到 Guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Slash 命令已全局同步（生效最长 1 小时，建议设置 DISCORD_GUILD_ID）")


# ===== GitHub Webhook 监听（事件驱动审查） =====
async def post_pm_report(content: str):
    """主动推送中文汇报到 #pm-reports webhook（UTF-8 字节）"""
    if not PM_REPORT_WEBHOOK:
        print(f"[PM_REPORT] {content[:200]}")
        return
    payload = {"username": "Claude PM (系统)", "content": content[:1900]}
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(PM_REPORT_WEBHOOK, json=payload)


async def auto_review_pr(pr_number: int, action: str):
    """收到 PR 事件后自动审查并推送结果到 Discord"""
    try:
        pr = await gh_get(f"/repos/{REPO}/pulls/{pr_number}")
        files = await gh_get(f"/repos/{REPO}/pulls/{pr_number}/files")
        # 拉前 5 个变更文件 + 关联 Issue 验收标准
        file_summary = "\n".join(
            f"  {f['status']} {f['filename']} (+{f['additions']} -{f['deletions']})"
            for f in files[:30]
        )

        body = pr.get("body") or ""
        # 从 body 里提取 "Closes #N" 关联的 Issue
        import re
        issue_match = re.search(r"Closes\s+#(\d+)", body, re.IGNORECASE)
        issue_ctx = ""
        if issue_match:
            try:
                issue = await gh_get(f"/repos/{REPO}/issues/{issue_match.group(1)}")
                issue_ctx = f"\n\n关联 Issue #{issue['number']} 标题：{issue['title']}\n验收标准摘录：\n{(issue.get('body') or '')[:1500]}"
            except Exception:
                pass

        prompt = f"""你是 Claude PM，审查这个刚提交的 PR：
PR #{pr_number}: {pr['title']}
分支：{pr['head']['ref']}
PR 描述：{body[:800]}
变更文件：
{file_summary}{issue_ctx}

请给出 200 字以内的中文审查结论：
1. 通过 ✅ / 打回 ❌
2. 关键发现（命中验收标准、潜在风险、缺陷）
3. 建议下一步（CEO 直接合并 / 让开发修改）"""

        review = await ask_llm(prompt)
        await post_pm_report(
            f"**🔔 PR #{pr_number} 自动审查（事件触发）**\n"
            f"标题：{pr['title']}\n"
            f"事件：{action}\n\n{review}\n\n"
            f"链接：{pr['html_url']}"
        )
    except Exception as exc:
        await post_pm_report(f"⚠️ PR #{pr_number} 自动审查失败：{exc}")


def verify_github_signature(body: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET or not sig_header:
        return False
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


async def github_webhook_handler(request: web.Request):
    body = await request.read()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(body, sig):
        return web.Response(status=403, text="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    data = json.loads(body.decode("utf-8"))

    # PR 打开 / 重新提交 / 准备审查 → 立即审查
    if event == "pull_request":
        action = data.get("action")
        if action in ("opened", "synchronize", "ready_for_review", "reopened"):
            pr_number = data["pull_request"]["number"]
            asyncio.create_task(auto_review_pr(pr_number, action))
            return web.json_response({"status": "review-scheduled", "pr": pr_number})

    return web.json_response({"status": "ignored", "event": event})


async def webhook_health(request: web.Request):
    return web.json_response({"status": "ok", "bot_user": str(client.user) if client.user else "init"})


async def start_webhook_server():
    app = web.Application()
    app.add_routes([
        web.post("/github-webhook", github_webhook_handler),
        web.get("/health", webhook_health),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    print(f"GitHub webhook 服务监听 http://0.0.0.0:{WEBHOOK_PORT}/github-webhook")


async def main():
    await start_webhook_server()
    await client.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
