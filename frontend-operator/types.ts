// 客服 exe 共享类型 (与后端 /operator/* + /xbox/* API 字段对齐)

export type Operator = {
  id: number;
  loginName: string;
  displayName: string;
  totpConfirmed: boolean;
  isActive: boolean;
};

export type LoginResponse = {
  token: string;
  operator: {
    id: number;
    loginName: string;
    displayName: string;
  };
};

// 可领账号 (GET /operator/available-accounts)
export type AvailableAccount = {
  id: number;
  accountNo: string | null;
  name: string;
  country: string; // "US" / "UK" / "JP" / "EU" / ...
  currency: string; // "USD" / "GBP" / "JPY" / "EUR" / ...
  loginEmail: string | null;
  exchangeRate: string | null;
  // CEO 2026-05-17: 客服领取前能看到的实时账号状态
  localBalance: string; // 当前余额
  status: string; // active / disabled / error / need_verification
  statusMessage: string | null;
  lastSyncedAt: string | null;
};

// CEO 2026-05-17: 客服"我的领取"卡片用 - 跟 AvailableAccount 同形, 多 claimId / claimedAt
// + pendingOrderCount(待补订单数, 用于禁用归还按钮 + 顶部黄条警告)
export type ClaimedAccount = AvailableAccount & {
  claimId: number;
  claimedAt: string | null;
  pendingOrderCount: number;
};

// 客服当前持有的领取 (GET /operator/operators/{id}/claims)
export type OperatorClaim = {
  id: number;
  accountId: number;
  operatorId: number;
  claimedAt: string;
  returnedAt: string | null;
  isActive: boolean;
  returnReason: string | null;
};

// 账号详情 (PR C: 客服在 exe 内查的字段)
export type XboxAccountDetail = {
  id: number;
  accountNo: string | null;
  name: string;
  country: string;
  currency: string;
  loginEmail: string | null;
  passwordPlain: string | null; // 解密后明文(客服用来登录 Microsoft)
  exchangeRate: string | null;
  localBalance: string; // 微软账号当前本币余额 (USD/GBP)
  status: string;
  statusMessage: string | null;
  lastSyncedAt: string | null;
};

// Microsoft 订单同步结果
export type SyncOrdersResult = {
  batchId: number;
  success: boolean;
  ordersAdded: number;
  ordersSkipped: number;
  balance: { currency: string; balance: string } | null;
  failure: { category: string; message: string } | null;
};

// 客服 exe 看的订单
// CEO 2026-05-12: 历史订单表 9 列 (账号编号 / 订单编号 / 类型 / 日期 / 商品名 /
//   经办人 / 收款方式 / 收款金额 / 备注) — 字段全部映射在这。
export type OperatorOrder = {
  id: number;
  accountId: number;
  accountNo: string | null;        // 账号编号
  orderNo: string;                  // 订单编号
  amountLocal: string;              // 本币金额(微软订单原始金额)
  currencyLocal: string;            // 本币币种 USD/GBP
  orderAt: string;                  // Microsoft 报告的下单时间(只精确到日, 补 12:00:00)
  createdAt: string;                // CEO 2026-05-14: 同步落库的中国时间(精确到秒, 表格"日期"列显示这个)
  saleDate: string | null;          // 销售日期(自动=orderAt)
  status: string;                   // 类型: pending_complete / converted
  productName: string | null;       // 商品名
  operatorName: string | null;      // 经办人
  salePrice: string | null;         // 收款金额
  saleCurrency: string | null;
  walletMethodId: number | null;     // CEO 2026-05-20 #134: 已废弃, 老订单还有值
  walletMethodLabel: string | null;  // 老收款方式 label
  walletItemId: number | null;       // CEO 2026-05-20 #134: 已废弃
  walletItemLabel: string | null;    // 老备注模板 label / 新订单冗余存钱包名
  walletPoolId: number | null;       // CEO 2026-05-20 #134: 真实钱包 id(直挂)
  remark: string | null;             // CEO 2026-05-12: 可自由填写
};

// 钱包设置 (复用 /xbox/wallet-settings)
// CEO 2026-05-20 #134: 已废弃, 留类型兼容老组件(后端永远返回空数组)。
export type WalletMethod = {
  id: number;
  code: string;
  label: string;
  isActive: boolean;
  currency: SaleCurrency | null;
  items: {
    id: number;
    code: string;
    label: string;
    walletPoolId: number;
    isActive: boolean;
  }[];
};

// CEO 2026-05-20 #134: 客服销售记录可选钱包(真实钱包, 来自 /xbox/wallet-pool-options)
export type SalesWallet = {
  id: number;
  name: string;
  currency: SaleCurrency;
  fullPath: string;
};

export type SalesWalletGroup = {
  groupCode: string;   // "TAIWAN" / "TAOBAO"
  groupLabel: string;  // "台湾" / "淘宝"
  wallets: SalesWallet[];
};

export type SaleCurrency = "CNY" | "USD" | "USDT" | "TWD";
