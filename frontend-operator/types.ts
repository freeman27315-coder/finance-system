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

// 账号详情 (PR C 用,先占位)
export type XboxAccountDetail = {
  id: number;
  accountNo: string | null;
  name: string;
  country: string;
  currency: string;
  loginEmail: string | null;
  hasPassword: boolean;
  localBalance: string; // 微软账号本币余额 (USD/GBP)
  status: string;
  statusMessage: string | null;
  lastSyncedAt: string | null;
};
