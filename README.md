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

## Agent 协作规则

- 主动工作期间默认每 90 秒轮询 GitHub 状态，范围包括 `ready-for-dev`、`in-progress`、`needs-revision`、PR review/comment、Issue 评论和 CI / check 状态。
- 收到新的可执行任务后，Agent 先向 CEO 反馈“已收到任务 #n，开始开发”，然后直接开工。
- 阻塞不是停止工作：关键字段乱码、字段缺失、业务名称不清、验收标准不明或指令冲突时，Agent 必须列出无法确认的字段并询问 CEO / PM，同时继续轮询其他可执行任务，不能空转。
- 会进入数据库 / API 合同的字段必须逐字确认，不能凭业务直觉补全。

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
