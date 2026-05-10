# Finance System 项目交接文档

> 更新日期：2026-05-08
> 用途：会话上下文耗尽时,新会话读此文档可快速接上工作。

---

## 项目概况

**仓库**：`freeman27315-coder/finance-system`
**本机路径**：`D:\github-team\finance-system`
**业务**：财务管理系统,覆盖资产/淘宝/台湾/XBOX/供应商钱包流水 + 多模块销售对账

### 团队
| 角色 | 称呼 | 备注 |
|---|---|---|
| CEO | freeman27315-coder | Windows 主机用户,业务负责人 |
| PM | Claude PM | 主会话(我),拆需求 / 审 PR / 合并 / 推 Discord |
| 后端 subagent | ropz | `.claude/agents/ropz.md`,**当前会话不可用,PM 直接干** |
| 前端 subagent | broky | `.claude/agents/broky.md`,**同上** |

### 技术栈
- **后端**：Python 3.12 + FastAPI + SQLAlchemy 2.0 (Mapped[]) + SQLite + Pydantic v2
- **前端**：Next.js 14 + TypeScript + Tailwind + shadcn/ui + React Query
- **后端**: 端口 8000 (`python -m uvicorn src.main:app --host 127.0.0.1 --port 8000`)
- **前端**: 端口 3000 (`npm run dev`,在 `frontend/` 目录)
- **DB**: SQLite `finance.db`,启动自动 `init_db()` + 种子数据

---

## 必读 Skill

`.claude/skills/` 下 3 个 skill,新会话**先读再行动**：

1. **`claude-pm-persona`** —— PM 身份 / 团队配置 / 沟通规则 / 中文 / Discord 推送 / PowerShell UTF-8
2. **`taobao-cashflow-rules`** —— 6 淘宝钱包金流口径(按业务日期 vs 操作日期)
3. **`discuss-before-execute`** —— **重要工作流**：
   - 业务需求**先讨论再执行**(列方案 + 关键问题让 CEO 拍板)
   - 跳过条件：单字段微调 / hotfix / 已对齐延伸 / 纯代码
   - 用大白话和 CEO 沟通,**不给代码 / SQL / 表名 / 字段名**
   - 默认**后端 + 前端 + 测试 + 数据迁移整套做完才汇报**(不在中间打断)

---

## 钱包结构（最关键的业务模型）

### 大类
- `ASSET_RMB` (CNY): 支付宝钱包/微信钱包等
- `ASSET_USDT` (USDT)
- `ASSET_USD` (USD): 顶级空,等需要时建子钱包
- `TAOBAO` (CNY): 3 家店,每家挂 group 总钱包
- `TAIWAN` (TWD): 顶级空(老 3 个 8591/银行卡/超商代收已软删)
- `VENDOR` / `XBOX`: 老逻辑钱包
- **`XBOX_SALES_LEDGER`** (理论值,启动自动建)

### 实际值结构（千牛/业务真实流水产生）
```
资产 RMB
└─ 支付宝钱包(group)
   ├─ 丙火网络支付宝 / TOM支付宝 / BOSS支付宝 / 小小电玩支付宝
└─ 微信钱包
   └─ 跳舞姬微信
资产 USDT: FREEMAN币安 / 张总币安
淘宝
├─ 丙火网络(总,group)→ 5 个 TAOBAO 钱包(银行卡/在途×2/冻结/可提现)
├─ 兔仔电玩(总,group)→ 6 个钱包(含店铺支付宝,B 类店铺)
└─ 小小电玩(总,group)→ 5 个钱包
```

### 理论值结构（XBOX 客服录入归口,启动自动建）
```
XBOX 销售归口(顶级 group)
├─ 淘宝渠道 → 丙火网络 / 兔仔电玩 / 小小电玩 (CNY)
├─ 台湾渠道 → 银行卡A / 银行卡B / 袋鼠8591 / 喵喵8591 / 存余额 (TWD)
└─ RMB 渠道 → TOM支付宝 (CNY)
```

### 对账映射（启动自动建 6 条）
| 理论值 | 实际值 |
|---|---|
| 丙火网络 | 丙火网络(总) + 丙火网络支付宝(资产 RMB) |
| 兔仔电玩 | 兔仔电玩(总,已含店铺支付宝) |
| 小小电玩 | 小小电玩(总) + 小小电玩支付宝(资产 RMB) |
| TOM支付宝 | TOM支付宝(资产 RMB) |
| 台湾 5 个理论值 | 暂无映射,CEO 后续手动加 |

---

## XBOX 完整业务流程

```
1. 加卡系统 → 入库账号(P2 自动,目前手动)
2. 客服建订单(订单号/本币金额/币种/订单时间) → 自动算 RMB 成本 = 本币 × 账号汇率
3. 客服补齐:销售日期/商品/经办人/收款方式→备注模板/售价/币种
4. 字段填齐 → 3 秒倒计时自动转销售记录(双保险,手动按钮也保留)
5. 同账号 + 同备注模板 → 合单(售价相加,叠加档支持)
6. 销售记录创建即 credit 售价进对应理论值钱包
7. 改销售记录:售价 diff 调整池 / 改备注模板触发拆单(老池 debit 新池 credit)
8. 对账:每天比理论 vs 实际,差异 = 客服填错 → 拆单纠错
```

---

## 关键业务规则

| 规则 | 详情 |
|---|---|
| 0.6% 淘宝手续费 | 淘宝订单 received 时 `fee = round(gross × 0.006, 2)` ROUND_HALF_UP |
| 7 天聚合解冻 | 微信确认收货 → mature_at = `confirmed_at + 7d` (精确到分秒) → 解冻进可提现 |
| 多币种校验 | 销售币种必须 = 钱包币种 (CNY/USD/USDT/TWD),硬拒绝 |
| 销售不能撤销但可改 | CEO 4B,改字段联动钱包余额 |
| 时间统一中国时区 | UTC+8 naive,`china_now()` 替代所有 `func.now()` |
| 日汇总按业务日期 | created_at 是导入日;对账用 confirmed_at/shipped_at;同日多笔合并;升序展示 |
| 资金池可挂任意大类 | CEO Q1A,但 XBOX 钱包设置默认只显示理论值(防客服误选) |
| 拆单老销售记录变 0 保留 | CEO Q5A,审计追溯用 |

---

## 当前状态（2026-05-08）

- **主干**: `1723fe2` (PR #117 合并)
- **测试**: 193/193 通过
- **后端 PID**: 15872 (端口 8000)
- **前端 PID**: 21956 (端口 3000)

### XBOX 页面 5 个 tab(已上线)
1. **账号管理** — 账号编号/邮箱/密码(AES)/状态/汇率/审计日志
2. **订单** — 建/补齐/拆单/历史/跳转销售/状态筛选/日期筛选
3. **销售记录** — 3 张汇总卡/日期筛选/Excel 导出/改字段/订单明细展开/变更历史/高亮跳转
4. **钱包设置** — method/item/资金池下拉(默认理论值)
5. **对账** — 理论 vs 实际差异/映射 CRUD/group 递归汇总

### 淘宝模块完整功能
- 千牛 Excel 导入(14 列)+ reconcile + 0.6% 费率 + 7 天聚合自动解冻
- 6 钱包结构 + 银行卡提现 + 转店铺支付宝(A/B 类店铺)
- 钱包日汇总(按业务日期,升序,5 个钱包都支持)
- 3 家店 group 总钱包(对账用)

---

## 关键文件路径

### 后端
| 文件 | 用途 |
|---|---|
| `src/main.py` | FastAPI app + lifespan 初始化 |
| `src/database.py` | SQLite 配置 + 自动迁移 |
| `src/utils/time.py` | `china_now()` UTC+8 naive |
| `src/utils/crypto.py` | AES-256-GCM (XBOX 密码加密) |
| `src/services/taobao.py` | 淘宝默认钱包 + **`ensure_shop_total_group_wallets`** (店铺总钱包) |
| `src/services/taobao_import.py` | 千牛导入 + reconcile + 7 天解冻 |
| `src/services/taobao_maturity.py` | 聚合到期 release 服务 |
| `src/services/xbox_account.py` | XBOX 账号 CRUD + 审计 |
| `src/services/xbox_order.py` | XBOX 订单 + 拆单 `move_order_to_different_sale_record` |
| `src/services/xbox_sale.py` | XBOX 销售记录 + 合单 + 改字段联动 + `get_sales_summary` |
| `src/services/xbox_wallet_setting.py` | XBOX 钱包设置 (method/item) |
| `src/services/xbox_sales_ledger.py` | 理论值钱包初始化 + 默认 method 预设 + **`ensure_xbox_default_reconcile_mappings`** |
| `src/services/xbox_reconcile.py` | 对账核心 + group 递归汇总 |
| `src/routers/xbox.py` | XBOX 所有端点 (15+ 个) |
| `src/routers/taobao.py` | 淘宝端点 + `daily-summary` |
| `src/models/wallet.py` | Wallet + WalletTransaction (含 `business_date`) |
| `src/models/xbox.py` | 9 张 XBOX 表 |

### 前端
| 文件 | 用途 |
|---|---|
| `frontend/types.ts` | 全局类型 |
| `frontend/lib/api.ts` | 所有 API 封装 |
| `frontend/components/xbox-page.tsx` | XBOX 5 tab 主页(超长,1700+ 行) |
| `frontend/components/taobao-page.tsx` | 淘宝主页 |

### Skill / 配置
| 文件 | 用途 |
|---|---|
| `.claude/skills/claude-pm-persona/SKILL.md` | PM 身份 |
| `.claude/skills/taobao-cashflow-rules/SKILL.md` | 淘宝金流口径 |
| `.claude/skills/discuss-before-execute/SKILL.md` | 工作流约束(关键) |
| `.env` (gitignore) | `XBOX_ACCOUNT_PASSWORD_KEY=` AES 密钥 |
| `~/.claude/.../memory/discord_webhooks.md` | Discord webhook URL |

---

## CEO 口径关键决策（按时间序）

| 决策 | 选择 |
|---|---|
| 淘宝平台费率 | 0.2% → **0.6%** |
| mature_at 算法 | 按日 → **精确到分秒**(PR #90) |
| 系统时间 | **统一中国时区** UTC+8 |
| 日汇总日期 | **业务日期**(confirmed_at/shipped_at)非操作日 |
| 同日合并 | 同 business_date 的 release IN 累加 |
| 排序 | 升序(旧→新) |
| 多币种 | RMB/USD/USDT/TWD 都支持 |
| RMB 成本 | 本币 × 账号汇率 |
| 销售记录入账 | 创建即 credit 售价(Q2A) |
| 销售可改不可撤销 | 4B,改字段联动 |
| 资金池范围 | 全部钱包大类(Q1A) |
| 币种校验 | 硬校验拒绝(Q2A) |
| 3 秒自动保存 | 双保险 + 手动按钮(Q4A) |
| 拆单老记录变 0 | 保留(Q5A) |
| 理论值大类 | 新建 XBOX_SALES_LEDGER 物理隔离(Q1A) |
| 钱包设置下拉 | 默认只显示理论值(Q2A) |
| 老台湾 3 钱包 | 软删除(Q3B) |
| 店铺总钱包 | 建 group 容器(B 方案) |
| 店铺支付宝归属 | 用 1:N 映射挂(A) |
| 对账周期 | 按日(Q2A) |
| 实际值取数 | 当天 IN 流水总额(Q3A) |
| 差异处理 | 仅展示让 CEO 拆单(Q4A) |

---

## 下一步可能方向（CEO 还没确认）

| 优先级 | 方向 | 估时 |
|---|---|---|
| 高 | Microsoft 自动同步抓订单(RPA/Playwright) | 2-3 天,大工程 |
| 高 | 加卡系统接口对接(IF-01) | 1 天 + 联调 |
| 中 | 退款 / 作废流程 | 0.5 天 |
| 中 | 整体财务面板(跨模块总览 + 趋势) | 1-2 天 |
| 低 | 客户管理 / 经办人业绩 / 权限分级 | 各 1-2 天 |

---

## 上下文压缩 / 新会话接入 SOP

1. **读 3 个 skill** (`.claude/skills/`)
2. **读本文件** (`docs/PROJECT_HANDOFF.md`)
3. **检查后端/前端进程**:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000,3000 -State Listen
   ```
4. **跑测试确认状态稳定**: `python -m pytest tests/`
5. **Discord 推送规则**:
   ```powershell
   $url = "https://discord.com/api/webhooks/1498286886131597406/W9zzS-L5ZYDs-YVeLpEgAaU3VK_RcWZkronjADfNicoY0aGiFc_IDvU_ZqOUCyMosCQv"
   $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ username = "Claude PM"; content = "中文" } | ConvertTo-Json -Compress))
   Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes
   ```

---

## 与 CEO 沟通的关键习惯

- **直接、不绕弯**：先结论后数据,不写"好的"/"非常感谢"
- **业务语言**：CEO 不懂代码,**绝不展示 SQL/字段名/JSON**,用大白话 + 例子
- **决策对齐**：业务需求按 4-5 个 Q 列选项,每个给推荐
- **执行节奏**：业务对齐完 → 一气呵成做完 → 一次汇报(浏览器能看到才算完工)
- **Discord 同步**：每次合并 / 完工都推 #pm-reports
- **歧义停下问**：发现新业务点不要默默做错,立即停下来问

---

## 当前最后一次操作

PR #117 (commit `1723fe2`) - 店铺总钱包 + 对账自动映射 + group 递归汇总。

CEO 试用清单：
1. 刷新 `http://127.0.0.1:3000/xbox` (Ctrl+Shift+R)
2. 对账 tab 选今天 → 看 9 个理论值钱包,前 4 个有自动映射
3. 5/6 丙火网络对账：理论 ¥0 vs 实际 ¥422,300 → 差异 -¥422,300（数据库里 5/6 那次大批量导入的真实值）
