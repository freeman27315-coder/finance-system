#!/bin/bash
# Codex Listener - 监听 inbox 文件，新任务出现就喂给 codex 处理
#
# 用法（在 Mac 上单独一个终端窗口运行，与 webhook server 并行）：
#   chmod +x codex_listener.sh
#   ./codex_listener.sh
#
# 工作流：
#   agent webhook server 收到 GitHub 事件 → 写任务到 ~/finance-system-tasks/issue-N.md
#   → append 路径到 ~/finance-system-tasks/inbox.txt
#   → 本脚本 tail -f 监听到新行 → cat 任务内容 → codex exec 处理
#
# 环境变量（可选）：
#   TASKS_DIR    任务目录（默认 ~/finance-system-tasks）
#   INBOX_FILE   inbox 文件（默认 $TASKS_DIR/inbox.txt）
#   CODEX_CMD    codex 命令模板（默认 "codex exec"）

set -uo pipefail

TASKS_DIR="${TASKS_DIR:-$HOME/finance-system-tasks}"
INBOX_FILE="${INBOX_FILE:-$TASKS_DIR/inbox.txt}"
CODEX_CMD="${CODEX_CMD:-codex exec}"

mkdir -p "$TASKS_DIR"
touch "$INBOX_FILE"

echo "=== Codex Listener 启动 ==="
echo "  inbox: $INBOX_FILE"
echo "  CMD: $CODEX_CMD"
echo "  等待新任务..."
echo ""

# tail -fn0 = 从文件末尾开始监听新行（不读历史内容）
tail -fn0 "$INBOX_FILE" | while IFS= read -r task_file; do
    # 跳过空行和不存在的文件
    [ -z "$task_file" ] && continue
    if [ ! -f "$task_file" ]; then
        echo "⚠️  任务文件不存在: $task_file" >&2
        continue
    fi

    echo ""
    echo "📥 [$(date '+%H:%M:%S')] 收到新任务: $task_file"
    echo "─────────────────────────────────────────"

    # 把任务文件内容作为 prompt 喂给 codex
    prompt=$(cat "$task_file")

    # 启动 codex 处理（后台运行，不阻塞下一个任务）
    # 注意：codex 一次执行一个任务，等它完成；如要并行可改 & 后台
    if echo "$prompt" | $CODEX_CMD; then
        echo "✅ codex 已处理 $task_file"
    else
        echo "❌ codex 处理失败（exit $?），任务文件保留供手工处理"
    fi
    echo "─────────────────────────────────────────"
done
