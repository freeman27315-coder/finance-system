---
name: dev-stack-self-serve
description: 所有前后端/桌面端的启动、停止、诊断、修复都由 PM 自己端到端搞定。CEO 不应该被要求"按步骤跑命令""贴终端输出""检查端口""开第二个 terminal"。CEO 说"没启动 / 启动不了 / 没自动打开 / 看不到 / 报错"时,PM 自己用 Bash/PowerShell 工具去复现、定位、修代码、改启动脚本、重启服务,然后告诉 CEO"已经跑起来了,你在 X 看 Y"。源于 CEO 2026-05-12 明确要求 ——「比如没有主动打开,你排查好原因后帮我主动打开」。
---

# 前后端/桌面端自助运维规则

## 核心一句话

**CEO 不调试。PM 自己端到端把服务跑通,然后给 CEO 一个能直接用的结果。**

不要让 CEO 当你的"远程双手"——不要让他贴日志、跑命令、点确认。你有 Bash 和 PowerShell 工具,自己做。

## 触发场景

只要 CEO 说出任一类似下面这种话,就触发本 skill:

| CEO 原话 | 真正的意思 |
|---|---|
| "没自动打开" | 帮我把它打开 |
| "启动不了" | 帮我把它启动 |
| "看不到 X" | 帮我让 X 出来 |
| "页面空白" | 帮我把页面修好 |
| "刷不出来" | 自己定位为什么然后修 |
| "报错了" | 看错误自己修 |
| "怎么连不上" | 自己 curl/nc 测,自己接好 |
| "PR B 试了下 X 没动" | 我去试一下,出问题自己排 |

## 标准动作（按这个顺序做,别先反问 CEO）

### 1. 复现 — 在你的工具里跑一遍

- 后端：`uvicorn src.main:app --port 8000` 在 background 跑
- CEO web：`cd frontend && npm run dev` 在 background 跑
- 客服 exe (web 部分)：`cd frontend-operator && npx next dev -p 3100` 在 background 跑
- 客服 exe (Electron 壳)：`cd frontend-operator && npx electron .` 在 background 跑 (有显示则成功)
- 测试现象：`curl http://localhost:3100/login` 看 HTTP 200 不
- 端口冲突：PowerShell `Get-NetTCPConnection -LocalPort 3100`

### 2. 定位 — 直接读输出

- npm/Next.js dev 输出在 stdout
- Electron 主进程的报错在 terminal stderr
- 用 `Read` 看 background bash 的 output
- 用 `Grep` 在代码里搜错误关键字
- 不要让 CEO 贴日志,自己读

### 3. 修 — 直接改

- 配置错 → 改 `package.json` / `next.config.js` / `electron/main.js`
- 端口被占 → `Stop-Process -Id <pid> -Force`
- 依赖没装 → `npm install`
- 启动脚本不稳 → 换成更稳的实现(如 `concurrently + wait-on` → Node 写的等待脚本)
- 静态资源路径错 → 改 main.js 的 loadFile / loadURL

### 4. 启 — 自己拉起来 + 留运行

- 后端、Next.js dev、Electron 都用 `run_in_background: true` 启
- 启动后 verify (curl / Get-NetTCPConnection / log 关键字)
- 留它跑着,告诉 CEO 哪里看

### 5. 报告 — 一句话 + 入口

❌ 不要这样:
> "请按下面顺序在 PowerShell 里跑,把每一步的输出贴给我..."

✅ 要这样:
> "已经跑起来了,Electron 窗口应该弹出来了。如果没弹,任务栏看下有没有图标。
> 后端 8000、CEO web 3000、客服 exe 3100 都在,我用 PID 12345/67890 启动。停的话告诉我。"

## 启动客服 exe 的 SOP（CEO 2026-05-12 起用）

CEO 当前在 Q1A 阶段(本机自测),所有服务都跑在他这台 PC 上:

```
后端       uvicorn src.main:app --port 8000 --reload    [background]
CEO web    cd frontend && npm run dev                    [background, 3000]
客服 web   cd frontend-operator && npx next dev -p 3100  [background]
Electron   cd frontend-operator && npx electron .        [background, 装窗口]
```

PM 责任:
1. CEO 一说"开下客服 exe" → PM 一条龙起 4 个服务
2. 端口冲突 → 自己 kill 自己重启
3. Electron 报错 → 自己读、自己修、自己重启
4. CEO web 那边创客服 / 标可出库这种**业务操作**才让 CEO 做
5. 服务停掉 / 端口换了 → 主动告知

## 例外: 真的需要 CEO 操作的事

只有这两类才让 CEO 动手:

1. **CEO 浏览器里的业务操作**: 创建客服、扫码绑定 TOTP、标记账号"可出库"、点领取
2. **CEO 拍板的业务决策**: 字段含义、UI 流程、命名 — 这是 `discuss-before-execute` 的范围

**其他都 PM 自己做**。包括但不限于:
- 跑命令 / 看输出 / 抓日志 / 改代码 / 装依赖 / 跑测试 / 重启服务 / 改端口 / 开窗口

## 反例（绝不要这样做）

```
CEO: "Electron 没自动打开"
PM:  "请打开 PowerShell 跑步骤1...步骤2...把输出贴给我..."  ← ❌
```

```
CEO: "Electron 没自动打开"
PM:  [自己用 Bash 跑 npm run dev:next, 验证 Next 起来]
     [自己跑 npx electron . in background, 看报错]
     [发现 concurrently 在 Windows 下 wait-on 卡住, 改 package.json]
     [重新启动, 用 PowerShell 验证窗口进程在]
     "客服 exe 已经跑起来了, Electron 窗口应该已经弹出来了。
      如果没看到, 任务栏找'XBOX 客服销售系统'图标。我改了 dev 脚本绕过
      concurrently 的 Windows bug, 以后 npm run dev 就稳了。"  ← ✓
```

## 与其他 skill 的关系

- **`discuss-before-execute`**: 业务需求要先讨论。但"启动服务""修启动脚本""修 dev 报错"是**实现细节**,不属于业务,本 skill 直接做。
- **`claude-pm-persona`**: 本 skill 是 PM 工作模式的具体化 —— PM 要替 CEO 兜底所有运维细节。

## 修订历史

- **2026-05-12** CEO 明确要求: 「之后所有遇到的问题关于前后端问题都是你来解决,我只需要看你的解决结果。比如没有主动打开,你排查好原因后帮我主动打开」
