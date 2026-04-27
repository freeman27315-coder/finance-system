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
