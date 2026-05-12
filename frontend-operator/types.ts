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
export type OperatorOrder = {
  id: number;
  accountId: number;
  orderNo: string;
  amountLocal: string;
  currencyLocal: string;
  orderAt: string;
  saleDate: string | null;
  status: string;
  productName: string | null;
  salePrice: string | null;
  saleCurrency: string | null;
  walletMethodId: number | null;
  walletItemId: number | null;
};

// 钱包设置 (复用 /xbox/wallet-settings)
export type WalletMethod = {
  id: number;
  code: string;
  label: string;
  isActive: boolean;
  items: {
    id: number;
    code: string;
    label: string;
    walletPoolId: number;
    isActive: boolean;
  }[];
};

export type SaleCurrency = "CNY" | "USD" | "USDT" | "TWD";
