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

// PR #103 (issue #102) 加的账号状态
export type XboxAccountStatus = "active" | "disabled" | "error" | "need_verification";

export type XboxAccount = {
  id: string;
  name: string;
  country: XboxCountry;
  currency: Currency;
  rmbCostMinor: number;
  localBalanceMinor: number;
  remark: string | null;
  createdAt: string;
  // PR #103 新字段
  accountNo: string | null;
  loginEmail: string | null;
  hasPassword: boolean;
  exchangeRate: number | null; // 账号固定汇率（取后端 string,前端转 number）
  status: XboxAccountStatus;
  statusMessage: string | null;
  lastSyncedAt: string | null;
};

// 账号变更审计日志
export type XboxAccountAuditLog = {
  id: string;
  accountId: string;
  action: "created" | "updated" | "password_changed" | "status_changed";
  detail: string | null;
  operator: string | null;
  createdAt: string;
};

// PR #110 P0.2 - 销售币种
export type XboxSaleCurrency = "CNY" | "USD" | "USDT" | "TWD";

// 订单状态
export type XboxOrderStatus = "pending_complete" | "converted";

// 同步订单（手动建或 Microsoft 抓取）
export type XboxOrder = {
  id: string;
  accountId: string;
  orderNo: string;
  amountLocal: number; // 本币金额（minor unit, 大金额）
  currencyLocal: string; // USD/GBP
  exchangeRate: number | null;
  rmbCost: number; // RMB 成本（minor unit）
  orderAt: string;
  status: XboxOrderStatus;
  // 补齐字段
  saleDate: string | null;
  productName: string | null;
  operatorName: string | null;
  salePrice: number | null;
  saleCurrency: XboxSaleCurrency | null;
  walletMethodId: string | null;
  walletItemId: string | null;
  saleRecordId: string | null;
  createdAt: string;
  lastUpdatedAt: string;
};

// 销售记录
export type XboxSaleRecord = {
  id: string;
  accountId: string;
  saleDate: string;
  productName: string;
  operatorName: string;
  salePrice: number; // minor unit
  saleCurrency: XboxSaleCurrency;
  walletMethodId: string;
  walletItemId: string;
  walletItemLabel: string;
  walletPoolId: string;
  bookkeepingTxId: string | null;
  orderIds: string[];
  createdAt: string;
  lastUpdatedAt: string;
};

// 钱包设置 - 备注模板
export type XboxWalletItem = {
  id: string;
  code: string;
  label: string;
  walletPoolId: string;
  isActive: boolean;
};

// 钱包设置 - 收款方式
export type XboxWalletMethod = {
  id: string;
  code: string;
  label: string;
  isActive: boolean;
  items: XboxWalletItem[];
};

// 资金池下拉选项（按钱包大类分组）—— GET /xbox/wallet-pool-options
export type XboxPoolOptionWallet = {
  id: string;
  name: string;
  currency: string;
  fullPath: string; // "RMB钱包 / 支付宝钱包 / 丙火网络支付宝"
};

export type XboxPoolOptionGroup = {
  groupCode: string; // XBOX_SALES_LEDGER / ASSET_RMB / TAOBAO / TAIWAN ...
  groupLabel: string; // XBOX 销售归口 / 资产 RMB / 淘宝 / 台湾
  wallets: XboxPoolOptionWallet[];
};

// 订单 / 销售记录变更日志（GET /xbox/orders/{id}/change-logs 等）
export type XboxChangeLog = {
  id: string;
  entityType: "order" | "sale_record";
  entityId: string;
  action: "created" | "updated" | "completed" | "merged" | "wallet_pool_changed";
  detail: string | null;
  operator: string | null;
  createdAt: string;
};

// 对账映射（理论值钱包 ↔ 实际值钱包）
export type XboxReconcileMapping = {
  id: string;
  theoreticalWalletId: string;
  actualWalletId: string;
  createdAt: string;
};

// 对账报告每行（一个理论值钱包 + 它配对的实际值钱包们）
export type XboxReconcileReportRow = {
  theoreticalWallet: { id: string; name: string; currency: string };
  actualWallets: { id: string; name: string; currency: string; total: string }[];
  theoreticalTotal: string;
  actualTotal: string;
  diff: string;
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
// Taobao（PR #65/#67/#69/#73 后的新结构：3 店铺 × 5 钱包 + storeAlipayWallet 必填带 type）
// ---------------------------------------------------------------------------

// PR #73：storeAlipayWallet.type 表示该"店铺支付宝"挂在哪一类资产树
// - "ASSET_RMB"：丙火/小小，子钱包挂在资产支付宝下，是真实金流
// - "TAOBAO"：兔仔，子钱包挂在淘宝模块下，账面记账（钱不在我手）
export type StoreAlipayType = "ASSET_RMB" | "TAOBAO";

export type TaobaoShopWallet = {
  id: string;
  name: string;
  balanceMinor: number;
};

export type TaobaoStoreAlipayWallet = TaobaoShopWallet & {
  type: StoreAlipayType;
};

export type TaobaoShop = {
  id: string;
  name: string;
  storeAlipayWallet: TaobaoStoreAlipayWallet;
  unconfirmedAlipay: TaobaoShopWallet;
  unconfirmedWechat: TaobaoShopWallet;
  aggregatorFrozen: TaobaoShopWallet;
  aggregatorAvailable: TaobaoShopWallet;
  bankCard: TaobaoShopWallet;
  // PR #81/#82：聚合冻结钱包内"已到期、可一键解冻"的实时聚合数据
  // 仅用于前端 UI 显示"待解冻 ¥X (N 笔)"，与 aggregatorFrozen.balanceMinor 不冲突
  aggregatorMaturedAmountMinor: number;
  aggregatorMaturedCount: number;
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

// 钱包按日汇总（每天 IN / OUT / 净 / 笔数）—— 见 GET /taobao/shops/{id}/wallets/{wid}/daily-summary
export type TaobaoWalletDailySummary = {
  date: string; // YYYY-MM-DD（中国本地）
  inAmountMinor: number;
  outAmountMinor: number;
  netAmountMinor: number;
  count: number;
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
  // PR #85：本次导入末尾自动结算（autoRelease + 手续费扣减）
  // - autoReleasedAmountMinor / autoReleasedCount：本次自动解冻的金额 + 笔数
  // - totalFeeAmountMinor：本次导入产生的手续费总和
  autoReleasedAmountMinor: number;
  autoReleasedCount: number;
  totalFeeAmountMinor: number;
  errors: string[];
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
