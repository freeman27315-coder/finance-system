# Mac M4 Dev Agent 部署指南

## 工作流程

```
GitHub Issue (ready-for-dev)
        ↓ Webhook
  Mac Dev Agent (main.py)        ← 标记 in-progress，终端提示认领
        ↓
  开发者阅读 Issue，写代码
        ↓
  python github_helper.py submit <issue_number>
        ↓
  自动推送分支 + 创建 PR (in-review)
        ↓
  Claude PM 审查
```

## 第一步：安装依赖

```bash
# 安装 Homebrew（如未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 gh CLI
brew install gh

# 安装 cloudflared（用于 Webhook 公网穿透）
brew install cloudflared
```

## 第二步：克隆仓库并配置

```bash
git clone https://github.com/freeman27315-coder/finance-system.git
cd finance-system/agent

cp .env.example .env
```

编辑 `.env`，填入这些值：

```
GITHUB_TOKEN=ghp_...        # 与 Windows 端相同的 Token
WEBHOOK_SECRET=...          # 随机字符串，用以下命令生成：
AGENT_LABEL=backend         # backend 或 frontend
```

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 多 Agent 配置隔离

不要让 backend / frontend 共用同一个 `.env`。分别复制：

```bash
cp .env.backend.example .env.backend
cp .env.frontend.example .env.frontend
```

然后分别填入相同的 `GITHUB_TOKEN` / `WEBHOOK_SECRET`，但保持：

```bash
# .env.backend
AGENT_LABEL=backend

# .env.frontend
AGENT_LABEL=frontend
```

启动时使用对应脚本：

```bash
./start_backend.sh
# 或
./start_frontend.sh
```

这样 backend 和 frontend 的任务标签不会互相覆盖。

## 第三步：gh CLI 登录

```bash
echo "$GITHUB_TOKEN" | gh auth login --with-token
git config --global user.email "your@email.com"
git config --global user.name "Your Name"
```

## 第四步：安装 Python 依赖并启动

```bash
pip3 install -r requirements.txt
```

启动 Webhook 服务（保持终端开着）：
```bash
source .env
export GITHUB_TOKEN WEBHOOK_SECRET AGENT_LABEL GH_PATH
uvicorn main:app --host 0.0.0.0 --port 8080
```

另开一个终端，启动 Cloudflare Tunnel：
```bash
cloudflared tunnel --url http://localhost:8080
```

记录显示的公网地址，例如：
```
https://abcd-1234.trycloudflare.com
```

## 第五步：配置 GitHub Webhook

1. 打开 https://github.com/freeman27315-coder/finance-system/settings/hooks
2. 点击 **Add webhook**，填写：
   - Payload URL: `https://abcd-1234.trycloudflare.com/webhook`
   - Content type: `application/json`
   - Secret: `.env` 中的 `WEBHOOK_SECRET`
   - Events: **Issues** 和 **Pull requests**
3. 点击 **Add webhook**

验证服务正常：
```bash
curl https://abcd-1234.trycloudflare.com/health
# {"status":"ok","agent":"Dev Agent"}
```

## 日常开发流程

### Webhook / 事件驱动规则（零轮询）

- **完全由 GitHub 事件触发**：`main.py` 收到 webhook 后做三件事：
  1. 更新 Issue / PR 标签（in-progress / needs-revision）
  2. 写完整任务到 `~/finance-system-tasks/issue-N.md`（或 `TASKS_DIR` 指定的目录）
  3. 终端醒目打印 + macOS 桌面通知
- **开发者用 ChatGPT 的工作流：** 收到通知后打开 ChatGPT 网页/桌面版，把 `issue-N.md` 文件内容粘贴给 ChatGPT 让它按"工作流"部分干活。
- **开发者用 Claude Code 的工作流：** 在 `.env` 设置 `AGENT_DISPATCH_CMD=claude -p "请完成任务 #{issue_number}..."`，agent 收到事件后会自动 Popen 启动 Claude CLI。
- **触发动作映射：**
  - 收到 `ready-for-dev` + 本 agent 标签 → 标 in-progress + 通知开发者
  - 收到 PR `changes_requested` review → 标 needs-revision + 把 review 意见写进任务文件，让 ChatGPT 按 review 修
- **AI 助手的工作约束：**
  - 收到任务先在 Issue/PR 评论反馈「已收到任务 #N，开始开发」，然后直接开工，不要请求二次同意
  - 发现需求里关键字段乱码、缺失、业务名称不清、验收标准不明、指令冲突时，**立即在 Issue 评论 @CEO/@PM** 列出无法确认的字段，等待确认；不要凭直觉补全
  - 会进入数据库 / API 合同的字段（钱包名、币种、状态枚举、接口路径、金额方向、角色名、数据库字段名）必须逐字按需求实现
- **不能凭轮询补救漏接的事件**：如果怀疑事件漏掉了（例如 cloudflared 隧道临时挂掉），让 PM 重派 Issue 即可，不要主动每隔 N 秒去 GitHub 拉

**收到任务通知后：**
```bash
# 1. 开始开发（自动创建分支）
python github_helper.py start <issue_number>

# 2. 写代码...

# 3. 提交 PR
git add -A
git commit -m "feat: 实现 XXX 功能"
python github_helper.py submit <issue_number>
```

**查看当前待开发任务：**
```bash
python github_helper.py list
```
