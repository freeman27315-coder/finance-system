#!/bin/bash
# Deprecated wrapper: do not use shared .env for labeled agents.

set -euo pipefail

cat <<'EOF'
通用 start.sh 已停用，避免 backend / frontend 共用 .env 导致串单。

请改用专用启动脚本：
  ./start_backend.sh
  ./start_frontend.sh

对应配置文件：
  .env.backend
  .env.frontend
EOF

exit 1
