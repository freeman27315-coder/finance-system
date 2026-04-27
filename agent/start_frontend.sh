#!/bin/bash
# Frontend Dev Agent 启动脚本。只读取 .env.frontend，避免误改 backend 配置。

set -euo pipefail

ENV_FILE=".env.frontend"
PORT="${PORT:-8085}"
TUNNEL_URL="http://localhost:${PORT}"

echo "=== Frontend Dev Agent 启动 ==="

if [ ! -f "$ENV_FILE" ]; then
    cp .env.frontend.example "$ENV_FILE"
    echo "请先编辑 $ENV_FILE 填入 Token/Secret，然后重新运行"
    exit 1
fi

pip3 install -r requirements.txt -q

set -a
source "$ENV_FILE"
set +a

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export GITHUB_TOKEN WEBHOOK_SECRET AGENT_LABEL GH_PATH LANG LC_ALL PYTHONUTF8 PYTHONIOENCODING

if [ "${AGENT_LABEL}" != "frontend" ]; then
    echo "$ENV_FILE 中 AGENT_LABEL 必须是 frontend"
    exit 1
fi

uvicorn main:app --host 0.0.0.0 --port "$PORT" &
AGENT_PID=$!
echo "Frontend Agent 已启动 PID: $AGENT_PID, port: $PORT"

echo ""
echo "=== Cloudflare Tunnel 公网地址 ==="
cloudflared tunnel --url "$TUNNEL_URL"
