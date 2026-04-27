# Discord Bot 部署指南（Windows）

可在 Discord 直接 @ Bot 提问、用 Slash 命令管理项目。

## 第一步 — 你需要做的两件事

### 1. 创建 Discord Bot 拿 Token

1. 打开 https://discord.com/developers/applications
2. 点击 **New Application** → 名称填 `Claude PM` → Create
3. 左侧菜单选 **Bot** → 点 **Reset Token** → 复制（这就是 `DISCORD_TOKEN`）
4. 在 Bot 页面打开 **MESSAGE CONTENT INTENT** 开关
5. 左侧菜单选 **OAuth2** → URL Generator：
   - SCOPES 勾：`bot` + `applications.commands`
   - BOT PERMISSIONS 勾：`Send Messages`、`Read Message History`、`Use Slash Commands`、`Mention Everyone`
   - 复制底部生成的 URL，浏览器打开 → 选你的 Discord 服务器 → 授权

### 2. 拿 Anthropic API Key
1. 打开 https://console.anthropic.com/settings/keys
2. **Create Key** → 复制（这就是 `ANTHROPIC_API_KEY`，sk-ant- 开头）

### 3. （可选但推荐）拿 Discord Guild ID
1. Discord 设置 → 高级 → 打开 **开发者模式**
2. 右键你的服务器名 → **复制服务器 ID**（这就是 `DISCORD_GUILD_ID`）

---

## 第二步 — 填配置启动

```cmd
cd D:\github-team\finance-system\bot
copy .env.example .env
notepad .env
```

填入三个 Token 后保存关闭，运行：

```cmd
start.bat
```

看到 `已登录: Claude PM#xxxx` 就成功了。

---

## 在 Discord 怎么用

**@ 提问：**
```
@Claude PM 当前进度怎么样
@Claude PM 帮我看看 PR #17 有没有问题
```

**Slash 命令：**
- `/status` — 查看所有开放 PR/Issue
- `/review pr_number:17` — 让我审查 PR #17
- `/dispatch target:backend title:"加导出 CSV" body:"详细需求..."` — 直接派发任务

Bot 启动后保持窗口开着即可，关掉就停止。要后台跑可用 `pythonw main.py` 或 NSSM 打包成服务。
