# Mac M4 GPT Dev Agent 部署指南

## 第一步：安装 Homebrew（如未安装）
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

## 第二步：克隆仓库
```bash
git clone https://github.com/freeman27315-coder/finance-system.git
cd finance-system/agent
```

## 第三步：配置环境变量
```bash
cp .env.example .env
```
编辑 `.env` 文件，填入：
- `GITHUB_TOKEN` → 使用同一个 GitHub Token
- `OPENAI_API_KEY` → 你的 OpenAI API Key（sk-...）
- `WEBHOOK_SECRET` → 随机字符串，与 GitHub Webhook 配置一致

生成随机 Secret：
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 第四步：启动 Agent
```bash
chmod +x start.sh
./start.sh
```

启动后会显示类似：
```
https://xxxx-xxxx.trycloudflare.com
```
这就是 Webhook 的公网地址，复制下来。

## 第五步：配置 GitHub Webhook
1. 打开 https://github.com/freeman27315-coder/finance-system/settings/hooks
2. 点击 **Add webhook**
3. 填写：
   - Payload URL: `https://xxxx-xxxx.trycloudflare.com/webhook`
   - Content type: `application/json`
   - Secret: `.env` 中的 `WEBHOOK_SECRET`
   - Events: 选择 **Let me select individual events** → 勾选 **Issues** 和 **Pull requests**
4. 点击 **Add webhook**

## 验证
```bash
curl https://xxxx-xxxx.trycloudflare.com/health
# 返回: {"status":"ok","agent":"GPT Dev Agent"}
```
