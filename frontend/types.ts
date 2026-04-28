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

export type VendorSummary = {
  payableMinor: number;
  receivableMinor: number;
  netMinor: number;
  currency: Currency;
};

export type DashboardData = {
  wallets: WalletBalance[];
  vendorSummary: VendorSummary;
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

export type BillDirection = "payable" | "receivable";

export type BillStatus = "pending" | "settled";

export type Vendor = {
  id: string;
  name: string;
  remark: string | null;
  createdAt: string;
};

export type VendorBill = {
  id: string;
  vendorId: string;
  direction: BillDirection;
  amountMinor: number;
  currency: Currency;
  status: BillStatus;
  dueDate: string | null;
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

export type TaobaoWalletScope = "unsettled" | "settled";

export type TaobaoAccount = {
  id: string;
  name: string;
  unsettledWalletId: string;
  settledWalletId: string;
  unsettledBalanceMinor: number;
  settledBalanceMinor: number;
  remark: string | null;
  createdAt: string;
};

export type TaobaoTransaction = {
  id: string;
  walletId: string;
  walletScope: TaobaoWalletScope;
  amountMinor: number;
  direction: "in" | "out";
  remark: string | null;
  createdAt: string;
};

export type ModuleSection = {
  id: string;
  title: string;
  href: string;
  description: string;
  walletTypes: WalletType[];
};
