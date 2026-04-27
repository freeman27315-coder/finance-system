#!/usr/bin/env python3
"""Claude PM Discord Bot

功能：
1. @ 机器人 → Claude 回复（带项目上下文）
2. /status     查看所有 PR/Issue 状态
3. /review N   审查 PR #N
4. /dispatch backend|frontend "标题" "需求" 直接派发任务
"""
import os
import asyncio
import subprocess
from pathlib import Path

import discord
from discord import app_commands
from anthropic import Anthropic
import httpx

# ===== 配置 =====
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("GITHUB_REPO", "freeman27315-coder/finance-system")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 可选：指定服务器加速命令同步

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

claude = Anthropic(api_key=ANTHROPIC_API_KEY)
gh = httpx.AsyncClient(
    base_url="https://api.github.com",
    headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
    timeout=30,
)


SYSTEM_PROMPT = f"""你是 Claude PM，负责 GitHub 仓库 {REPO} 的 AI 团队管理。

团队成员：
- 考尔（backend）：在 Mac 上写 Python FastAPI 后端
- 壮壮（frontend）：在另一台机器上写 Next.js 前端
- 你（Claude PM）：在 Windows 上拆需求、审查代码、合并 PR、向用户汇报

工作流：
- 用户提需求 → 你创建带 backend/frontend 标签的 Issue
- 标签触发 Webhook 推到对应开发者
- 开发者写完提 PR → 你审查 → 合并并向用户汇报

回答风格：简洁、中文、有数据支撑。能用工具查的就别猜。"""


# ===== GitHub 帮助函数 =====
async def gh_get(path: str):
    r = await gh.get(path)
    r.raise_for_status()
    return r.json()


async def gh_post(path: str, data: dict):
    r = await gh.post(path, json=data)
    r.raise_for_status()
    return r.json()


async def list_open_prs():
    return await gh_get(f"/repos/{REPO}/pulls?state=open")


async def list_open_issues():
    return await gh_get(f"/repos/{REPO}/issues?state=open")


async def get_repo_status_summary() -> str:
    prs = await list_open_prs()
    issues = await list_open_issues()
    issues = [i for i in issues if "pull_request" not in i]

    lines = [f"**仓库状态：** {REPO}\n"]
    lines.append(f"**开放 PR ({len(prs)})：**")
    for p in prs[:10]:
        labels = ", ".join(l["name"] for l in p.get("labels", []))
        lines.append(f"  • #{p['number']} {p['title']}  [{labels}]")
    lines.append(f"\n**开放 Issue ({len(issues)})：**")
    for i in issues[:15]:
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        lines.append(f"  • #{i['number']} {i['title']}  [{labels}]")
    return "\n".join(lines)


# ===== Slash 命令 =====
@tree.command(name="status", description="查看仓库当前 PR / Issue 状态")
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        text = await get_repo_status_summary()
        await interaction.followup.send(text[:1900])
    except Exception as exc:
        await interaction.followup.send(f"查询失败：{exc}")


@tree.command(name="review", description="审查指定 PR")
@app_commands.describe(pr_number="PR 编号")
async def review_cmd(interaction: discord.Interaction, pr_number: int):
    await interaction.response.defer()
    try:
        pr = await gh_get(f"/repos/{REPO}/pulls/{pr_number}")
        files = await gh_get(f"/repos/{REPO}/pulls/{pr_number}/files")
        file_summary = "\n".join(f"  {f['status']} {f['filename']} (+{f['additions']} -{f['deletions']})" for f in files[:30])
        prompt = f"""请审查这个 PR：
标题：{pr['title']}
分支：{pr['head']['ref']}
正文：{pr.get('body', '')[:1000]}
变更文件：
{file_summary}

请给出 200 字以内的中文审查结论：通过 / 打回，关键问题。"""
        msg = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text
        await interaction.followup.send(f"**PR #{pr_number} 审查结果**\n\n{text}")
    except Exception as exc:
        await interaction.followup.send(f"审查失败：{exc}")


@tree.command(name="dispatch", description="派发新任务给指定开发者")
@app_commands.describe(target="backend 或 frontend", title="任务标题", body="任务详情")
@app_commands.choices(target=[
    app_commands.Choice(name="backend (考尔)", value="backend"),
    app_commands.Choice(name="frontend (壮壮)", value="frontend"),
])
async def dispatch_cmd(interaction: discord.Interaction, target: app_commands.Choice[str], title: str, body: str):
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


# ===== @ 提问回复 =====
@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or not client.user:
        return
    if client.user not in message.mentions:
        return

    content = message.content.replace(f"<@{client.user.id}>", "").strip()
    if not content:
        return

    try:
        # 注入仓库当前状态作为上下文
        status = await get_repo_status_summary()
        msg = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT + f"\n\n当前仓库快照：\n{status}",
            messages=[{"role": "user", "content": content}],
        )
        answer = msg.content[0].text
        # Discord 单条 2000 字符限制
        for chunk in [answer[i:i+1900] for i in range(0, len(answer), 1900)]:
            await message.channel.send(chunk)
    except Exception as exc:
        await message.channel.send(f"处理失败：{exc}")


@client.event
async def on_ready():
    print(f"已登录: {client.user}")
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"Slash 命令已同步到 Guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Slash 命令已全局同步（最多需要 1 小时生效，建议设置 DISCORD_GUILD_ID）")


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
