# 财务系统 - AI多智能体协作开发

## 架构

```
用户需求输入
    ↓
Claude PM (需求拆分 → 创建 GitHub Issues)
    ↓
GitHub (Issues / Projects / PRs 协调层)
    ↓ Webhook
GPT Dev Agent (Mac M4 - 读取任务 → 生成代码 → 提交 PR)
    ↓
Claude PM (代码审查 → 汇报结果)
```

## 标签说明

| 标签 | 含义 |
|------|------|
| `ready-for-dev` | 需求已拆分，等待 Agent 认领 |
| `in-progress` | Agent 正在开发中 |
| `in-review` | PR 已提交，等待 PM 审查 |
| `needs-revision` | 需要修改 |
| `done` | 已完成并合并 |
| `blocked` | 有阻塞需要人工介入 |

## Agent 协作规则（事件驱动，零轮询）

- **完全由 GitHub Webhook 事件触发**，agent 不再轮询 GitHub。`agent/main.py` 收到事件后会通过 `AGENT_DISPATCH_CMD`（默认 `claude -p`）激活本机 AI 编程助手立即开工。
- **触发动作映射：**
  - `ready-for-dev` 标签 + 本 agent label → 标 in-progress + 启动助手认领开发
  - PR `changes_requested` review → 标 needs-revision + 启动助手按 review 修复
- 收到任务后助手先向 CEO 反馈「已收到任务 #N，开始开发」，然后直接开工。
- 阻塞不是停止工作：关键字段乱码、字段缺失、业务名称不清、验收标准不明、指令冲突时，助手必须立即列出无法确认的字段在 Issue 评论里 @CEO/PM，等确认期间不要凭直觉补全。
- 会进入数据库 / API 合同的字段必须逐字按需求实现。

## 目录结构

```
├── .github/
│   └── ISSUE_TEMPLATE/    # Issue 模板
├── pm/                    # Claude PM 脚本 (Windows)
├── agent/                 # GPT Dev Agent (Mac M4)
├── docs/                  # 项目文档
├── frontend/              # Next.js 前端 Dashboard
└── src/                   # 财务系统源代码 (由 Agent 生成)
```

## Frontend

前端项目在 `frontend/`，独立于 Python 后端：

```bash
cd frontend
npm install
npm run dev
```

Next.js 会将 `/api/:path*` 代理到本地 FastAPI：`http://localhost:8000/:path*`。当前 Dashboard 使用 `GET /wallets/assets` 和 `GET /vendors/summary`，接口不可用时会使用本地 mock 数据。
