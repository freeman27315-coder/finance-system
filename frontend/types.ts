export type Currency = "CNY" | "USDT" | "USD" | "GBP" | "TWD";

export type WalletType = "ASSET_RMB" | "ASSET_USDT" | "VENDOR" | "XBOX" | "TAOBAO" | "TAIWAN";

export type WalletBalance = {
  id: string;
  name: string;
  type: WalletType;
  currency: Currency;
  balanceMinor: number;
  isGroup: boolean;
  children?: WalletBalance[];
  parentId?: string | null;
  remark: string | null;
  deletedAt: string | null;
};

export type DashboardData = {
  wallets: WalletBalance[];
};

export type AssetTransaction = {
  id: string;
  walletId: string;
  walletName: string;
  amountMinor: number;
  direction: "in" | "out";
  remark?: string | null;
  createdAt: string;
  currency: Currency;
};

export type Vendor = {
  id: string;
  name: string;
  remark: string | null;
  walletId: string;
  balanceMinor: number;
  createdAt: string;
};

export type VendorTransaction = {
  id: string;
  walletId: string;
  amountMinor: number;
  direction: "in" | "out";
  remark: string | null;
  createdAt: string;
};

export type XboxCountry = "US" | "UK";

export type XboxTransactionType = "recharge" | "consume";

export type XboxAccount = {
  id: string;
  name: string;
  country: XboxCountry;
  currency: Currency;
  rmbCostMinor: number;
  localBalanceMinor: number;
  remark: string | null;
  createdAt: string;
};

export type XboxTransaction = {
  id: string;
  accountId: string;
  rmbAmountMinor: number;
  localAmountMinor: number;
  type: XboxTransactionType;
  remark: string | null;
  createdAt: string;
  currency: Currency;
};

export type XboxCountrySummary = {
  rmbCostMinor: number;
  localBalanceMinor: number;
  accountCount: number;
  currency: Currency;
};

export type XboxSummary = {
  us: XboxCountrySummary;
  uk: XboxCountrySummary;
};

export type TaiwanWallet = {
  id: string;
  name: string;
  balanceMinor: number;
  createdAt: string;
};

export type TaiwanTransaction = {
  id: string;
  walletId: string;
  amountMinor: number;
  direction: "in" | "out";
  remark: string | null;
  createdAt: string;
};

export type TaiwanSummary = {
  totalBalanceMinor: number;
  walletCount: number;
};

// ---------------------------------------------------------------------------
// Taobao（PR #65/#67/#69 后的新结构：3 店铺 × 5 钱包 + paymentWallet 可空）
// ---------------------------------------------------------------------------

export type TaobaoShopWallet = {
  id: string;
  name: string;
  balanceMinor: number;
};

export type TaobaoShop = {
  id: string;
  name: string;
  paymentWallet: TaobaoShopWallet | null;
  unconfirmedAlipay: TaobaoShopWallet;
  unconfirmedWechat: TaobaoShopWallet;
  aggregatorFrozen: TaobaoShopWallet;
  aggregatorAvailable: TaobaoShopWallet;
  bankCard: TaobaoShopWallet;
  remark: string | null;
  createdAt: string;
};

export type TaobaoOrderPaymentMethod = "alipay" | "wechat";

export type TaobaoOrderStatus =
  | "shipped_unconfirmed"
  | "received"
  | "closed";

export type TaobaoOrder = {
  id: string;
  orderNumber: string;
  paymentMethod: TaobaoOrderPaymentMethod;
  amountMinor: number;
  status: TaobaoOrderStatus;
  bookkeepingWalletId: string | null;
  bookkeepingTxId: string | null;
  shippedAt: string | null;
  receivedAt: string | null;
  lastSyncedAt: string;
  recordedAt: string;
};

export type TaobaoWalletTransaction = {
  id: string;
  walletId: string;
  amountMinor: number;
  direction: "in" | "out";
  remark: string | null;
  createdAt: string;
  matureAt: string | null;
};

export type TaobaoImportReport = {
  shopName: string;
  totalRowsParsed: number;
  createdOrders: number;
  statusChangedOrders: number;
  closedReverted: number;
  skippedNoChange: number;
  skippedUnpaidOrUnshipped: number;
  skippedUnknownPayment: number;
  errors: string[];
};

export type TaobaoReleaseReport = {
  maturedCount: number;
  maturedAmountMinor: number;
  frozenBalanceAfterMinor: number;
  availableBalanceAfterMinor: number;
};

export type TaobaoFlowReport = {
  amountMinor: number;
  fromWalletId: string;
  fromWalletBalanceMinor: number;
  toWalletId: string;
  toWalletBalanceMinor: number;
  remark: string;
};

export type ModuleSection = {
  id: string;
  title: string;
  href: string;
  description: string;
  walletTypes: WalletType[];
};
