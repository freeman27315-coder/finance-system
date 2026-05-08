---
name: taobao-cashflow-rules
description: 淘宝 6 个钱包（店铺支付宝、支付宝在途、微信在途、聚合冻结、聚合可提现、银行卡）的金流口径规则 —— 「钱在哪天进/出钱包」该按订单业务日期还是系统操作日期。任何涉及淘宝钱包流水「日汇总 / 月汇总 / 业务报表」的需求都必须先读这个 skill,确保不把"导入 Excel 那天"当成业务日期。CEO 在 2026-05-08 明确确认了此口径。
---

# 淘宝金流口径规则

## 核心一句话

- 钱因为 **订单业务** 进/出钱包 → 按 **订单那天** 算（`shipped_at` / `confirmed_at`）
- 钱因为 **系统操作** 进/出钱包 → 按 **操作那天** 算（`WalletTransaction.created_at`）

## 6 钱包逐项口径

| 钱包 | 入账（IN）按哪天 | 出账（OUT）按哪天 |
|---|---|---|
| **店铺支付宝** | alipay/received 订单：`order.confirmed_at`<br>银行卡转入：`tx.created_at`（操作日） | 手动转出：`tx.created_at` |
| **支付宝在途** | alipay/shipped_unconfirmed 订单：`order.shipped_at` | 订单确认收货撤旧（reconcile）：`order.confirmed_at` |
| **微信在途** | wechat/shipped_unconfirmed 订单：`order.shipped_at` | 订单确认收货撤旧（reconcile）：`order.confirmed_at` |
| **聚合冻结** | wechat/received 订单：`order.confirmed_at` | 7 天后自动解冻 release：`tx.created_at`（即解冻当天） |
| **聚合可提现** | 自动解冻进账：`tx.created_at`（解冻当天） | 提现到银行卡：`tx.created_at`（操作日） |
| **银行卡** | 提现进账：`tx.created_at`（操作日） | 转店铺支付宝：`tx.created_at`（操作日） |

## 业务流程示例（CEO 确认过的口径）

### 例 1：纯支付宝路径
- 5/6 一个 ¥100 alipay 订单买家确认收货
- **店铺支付宝 5/6 +¥99.40**（按 `confirmed_at`,扣 0.6% 手续费）

### 例 2：微信走聚合（最复杂）
- 5/6 一个 ¥200 wechat 订单买家确认收货
- **聚合冻结 5/6 +¥198.80**（按 `confirmed_at`,扣 0.6%）
- 5/13 系统自动解冻（7 天后）
  - **聚合冻结 5/13 -¥198.80**（按解冻当天 `created_at`）
  - **聚合可提现 5/13 +¥198.80**（按解冻当天 `created_at`）
- 5/13 CEO 点"提现到银行卡"
  - **聚合可提现 5/13 -¥198.80**（按操作日）
  - **银行卡 5/13 +¥198.80**（按操作日）

### 例 3：在途状态切换
- 5/4 一个 ¥100 wechat 订单买家付款发货
- **微信在途 5/4 +¥100**（按 `shipped_at`）
- 5/6 买家确认收货,CEO 导入新 Excel
- **微信在途 5/6 -¥100**（按 `confirmed_at` —— 业务上钱"流出在途"的日期）
- **聚合冻结 5/6 +¥99.40**（按 `confirmed_at`）

## 为什么不用 `WalletTransaction.created_at`

`created_at` 是流水写入数据库的时间 = CEO 导入 Excel 那天。

如果按 `created_at` 聚合,会出现：
- CEO 5/8 才导入 5/6 ~ 5/8 三天的 Excel
- 日汇总只显示 5/8 一天有数据,5/6/7 都是 0
- **完全看不清真实业务节奏**

按业务日期就对了：5/6 看到的就是 5/6 真实成交的金额。

## 实现要点（给 ropz 写代码时参考）

### SQL 思路：LEFT JOIN `taobao_orders` ON `bookkeeping_tx_id`

```sql
SELECT
  CASE
    -- IN 流水有 order 关联 → 按 order 业务日期
    WHEN tx.direction = 'in' AND ord.id IS NOT NULL AND ord.status = 'received'
      THEN DATE(ord.confirmed_at)
    WHEN tx.direction = 'in' AND ord.id IS NOT NULL AND ord.status = 'shipped_unconfirmed'
      THEN DATE(ord.shipped_at)
    -- 其他（OUT、reconcile 撤旧、release、手动操作）→ 用 created_at
    ELSE DATE(tx.created_at)
  END AS business_date,
  ...
FROM wallet_transactions tx
LEFT JOIN taobao_orders ord ON ord.bookkeeping_tx_id = tx.id
WHERE tx.wallet_id = ?
GROUP BY business_date
ORDER BY business_date DESC
```

### 边界注意

1. **reconcile 撤旧**：状态变化时,`_handle_existing_order` 会 `_debit_old_tx` 撤老流水（OUT）+ 新 credit（IN）。
   - 老 OUT 流水的 `bookkeeping_tx_id` **指向自己之前**,但 reconcile 后 `order.bookkeeping_tx_id` 已经更新指向**新 IN**。所以老 OUT 在 LEFT JOIN 里 `ord.id IS NULL`,落入 ELSE 分支用 `created_at`。
   - **结论**：reconcile OUT 仍然按 `created_at`（操作日）。如果 CEO 想按 `confirmed_at`（订单确认收货那天）显示在途的撤出,需要单独识别"在途钱包 OUT + 同一订单存在 received 状态"。**默认先按 created_at,等 CEO 试用后再说。**

2. **聚合释放后清 mature_at**：PR #91 释放后 `tx.mature_at = None`,但 `bookkeeping_tx_id` 不变（order 仍引用该 tx）。所以聚合冻结的 IN 流水 JOIN 仍然成立,按 `confirmed_at` 算正确。

3. **手动操作流水（提现/转账）**：没有 `order` 关联,LEFT JOIN 无匹配,落入 ELSE 用 `created_at`。✓

4. **历史数据**：当前 4659 笔流水 `created_at` 都集中在 5/6（一次性导入）。新口径 LEFT JOIN order 后,IN 流水会按 `confirmed_at`/`shipped_at` 自动分散到各天。**不需要数据迁移**,前端展示靠实时 JOIN。

## 时区

`order.confirmed_at` / `shipped_at` 来自 Excel,naive 中国本地。`tx.created_at` 经 PR #92 后也是 naive 中国本地（`china_now()` 写入）。所以 `DATE()` 直接取 YYYY-MM-DD 就是中国日期。

## 当此口径不适用的情况

- 「我想看每次导入的报告」→ 用 `WalletTransaction.created_at`（导入日）—— 不是日汇总场景
- 「税务/对账/审计」需要"实际收到钱的日期" → 这就是这个 skill 的口径,正确
- 「一段时间内某钱包的余额变化」→ 是这个口径的累加,正确

## 触发本 skill 的场景

- CEO 提到"日汇总 / 月汇总 / 钱什么时候到 / 业务节奏 / 报表"且涉及淘宝钱包
- ropz 改 `daily-summary` 端点（或类似聚合端点）
- broky 改淘宝页时间维度展示
- 任何对 `WalletTransaction` 按日期 group 的需求

## 修订历史

- **2026-05-08** CEO 明确确认此口径（PR #94 / #96 上线后,实测数据按 `created_at` 不符合业务诉求,本 skill 记录正确口径供下次实现参考）
