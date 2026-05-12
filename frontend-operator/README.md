# XBOX 客服销售系统 (Electron + Next.js)

CEO 2026-05-12 决策: 给前端客服打包成 Windows 桌面 exe, 独立于 CEO 财务 web。

## 当前 PR B 范围

- ✅ Electron + Next.js + Tailwind 项目骨架
- ✅ 登录页 (三要素: 登录名 + 密码 + 6 位 TOTP)
- ✅ 工作台 (我领的账号 + 可领账号池 + 领取/归还按钮)
- ✅ JWT token + 客服信息存 localStorage, 路由守卫
- ⏳ PR C: 账号详情页(看密码 + 余额 + 同步订单 + 补销售信息)
- ⏳ PR D: 历史销售 + 打包 .exe

## 本机跑通(CEO 当前阶段: localhost 自测)

### 前置: 后端 + CEO web 跑起来
```bash
# 仓库根目录
uvicorn src.main:app --port 8000 --reload    # 后端
cd frontend && npm run dev                    # CEO web (3000) — 用来创建客服
```

CEO 在 http://localhost:3000/operators 创建客服 → 扫码绑定 TOTP → 标几个账号"可出库"。

### 启动客服 exe (开发模式)
```bash
cd frontend-operator
npm install
npm run dev   # 同时启 Next.js (3100) + Electron 窗口
```

Electron 窗口打开后:
1. 用刚创建的客服「登录名 + 密码 + Authenticator 6 位」登录
2. 看到工作台: 左边「我领的账号」(刚开始空) + 右边「可领账号池」
3. 点「领取」试一下 → 账号出现在左边
4. 点「归还」试一下 → 账号回到右边
5. 退出登录 / 再登录

> 仅跑 Web 浏览器调试(不开 Electron): `npm run start:web` 然后浏览器开 http://localhost:3100/login

## 项目结构

```
frontend-operator/
├── package.json          # scripts: dev / build / typecheck
├── next.config.js        # 静态导出 + /api/* 代理到 localhost:8000
├── electron/
│   ├── main.js           # Electron 主进程(开发=load URL, 生产=load file)
│   └── preload.js        # 渲染进程的桥(PR C 加 IPC: 复制密码等)
├── app/
│   ├── layout.tsx        # 全局 layout + QueryProvider
│   ├── globals.css       # Tailwind + 颜色变量(与 frontend/ 一致)
│   ├── page.tsx          # 工作台(useRequireAuth 守卫)
│   └── login/page.tsx    # 登录页
├── components/
│   ├── dashboard.tsx     # 工作台主体(我领的 + 可领池 + 退出)
│   ├── query-provider.tsx
│   └── ui/               # Button / Card / Badge / Table / Input
├── lib/
│   ├── api.ts            # /operator/login, /operator/claims, ...
│   ├── auth.ts           # token 存 localStorage + useRequireAuth
│   └── utils.ts          # cn() + 日期格式化
└── types.ts              # Operator / Claim / AvailableAccount
```

## 打包 .exe (PR D 上线)

```bash
cd frontend-operator
NEXT_EXPORT=1 npm run build:next    # 输出 out/ 静态文件
npm run build:electron              # 输出 release/*.exe
```

打包后的 `release/XBOX 客服销售系统 Setup 0.1.0.exe` 可以发给前端客服双击安装。

> ⚠️ 当前生产模式默认连 `http://localhost:8000`(本机), CEO Q5: 暂本机测,
> 后续迁服务器时改 `next.config.js` rewrites 目标即可(或走 env var)。
