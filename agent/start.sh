#!/bin/bash
# Mac M4 一键启动 GPT Dev Agent

set -e

echo "=== GPT Dev Agent 启动 ==="

# 检查 .env 文件
if [ ! -f .env ]; then
    cp .env.example .env
    echo "请先编辑 .env 文件填入 Token，然后重新运行"
    exit 1
fi

# 安装依赖
pip3 install -r requirements.txt -q

# 安装 gh CLI（如未安装）
if ! command -v gh &> /dev/null; then
    brew install gh
fi

# 安装 cloudflared（如未安装）
if ! command -v cloudflared &> /dev/null; then
    brew install cloudflared
fi

# 启动 FastAPI 服务（后台）
source .env
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export GITHUB_TOKEN OPENAI_API_KEY WEBHOOK_SECRET AGENT_LABEL GH_PATH LANG LC_ALL PYTHONUTF8 PYTHONIOENCODING
uvicorn main:app --host 0.0.0.0 --port 8080 &
AGENT_PID=$!
echo "Agent 已启动 PID: $AGENT_PID"

# 启动 Cloudflare Tunnel 获取公网 URL
echo ""
echo "=== Cloudflare Tunnel 公网地址 ==="
cloudflared tunnel --url http://localhost:8080
