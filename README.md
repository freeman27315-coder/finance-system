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

## 目录结构

```
├── .github/
│   └── ISSUE_TEMPLATE/    # Issue 模板
├── pm/                    # Claude PM 脚本 (Windows)
├── agent/                 # GPT Dev Agent (Mac M4)
├── docs/                  # 项目文档
└── src/                   # 财务系统源代码 (由 Agent 生成)
```
