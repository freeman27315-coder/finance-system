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
  country: string; // "US" / "UK"
  loginEmail: string | null;
  exchangeRate: string | null;
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
  orderAt: string;                  // 订单时间(=日期, 精确到秒)
  saleDate: string | null;          // 销售日期(自动=orderAt)
  status: string;                   // 类型: pending_complete / converted
  productName: string | null;       // 商品名
  operatorName: string | null;      // 经办人
  salePrice: string | null;         // 收款金额
  saleCurrency: string | null;
  walletMethodId: number | null;
  walletMethodLabel: string | null; // 收款方式 label
  walletItemId: number | null;
  walletItemLabel: string | null;   // 备注模板 label
  remark: string | null;            // CEO 2026-05-12: 可自由填写
};

// 钱包设置 (复用 /xbox/wallet-settings)
// CEO 2026-05-14: 后端推 method.currency 出来(该方式下所有 item 同币种),
// 前端选完方式自动锁币种,客服只填金额。
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

export type SaleCurrency = "CNY" | "USD" | "USDT" | "TWD";
