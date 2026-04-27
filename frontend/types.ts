export type Currency = "CNY" | "USDT" | "USD" | "GBP" | "TWD";

export type WalletType = "ASSET_RMB" | "ASSET_USDT" | "VENDOR" | "XBOX" | "TAOBAO" | "TAIWAN";

export type WalletBalance = {
  id: string;
  name: string;
  type: WalletType;
  currency: Currency;
  balanceMinor: number;
  parentId?: string | null;
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

export type Vendor = {
  id: string;
  name: string;
  remark?: string | null;
  createdAt?: string;
};

export type VendorBill = {
  id: string;
  vendorId: string;
  vendorName: string;
  direction: "payable" | "receivable";
  amountMinor: number;
  status: "pending" | "settled";
  dueDate?: string | null;
  remark?: string | null;
  createdAt?: string;
  currency: "CNY";
};

export type XboxCountry = "US" | "UK";

export type XboxAccount = {
  id: string;
  name: string;
  country: XboxCountry;
  currency: "USD" | "GBP";
  rmbCostMinor: number;
  localBalanceMinor: number;
  remark?: string | null;
  createdAt?: string;
};

export type XboxTransaction = {
  id: string;
  accountId: string;
  accountName: string;
  rmbAmountMinor: number;
  localAmountMinor: number;
  type: "recharge" | "consume";
  remark?: string | null;
  createdAt?: string;
  currency: "USD" | "GBP";
};

export type XboxSummary = {
  usRmbCostMinor: number;
  usLocalBalanceMinor: number;
  ukRmbCostMinor: number;
  ukLocalBalanceMinor: number;
};

export type TaobaoAccount = {
  id: string;
  name: string;
  unsettledWalletId: string;
  settledWalletId: string;
  unsettledBalanceMinor: number;
  settledBalanceMinor: number;
  remark?: string | null;
  createdAt?: string;
};

export type TaobaoTransaction = {
  id: string;
  walletId: string;
  walletScope: "unsettled" | "settled";
  amountMinor: number;
  direction: "in" | "out";
  remark?: string | null;
  createdAt?: string;
};

export type TaiwanWallet = {
  id: string;
  name: string;
  type: "TAIWAN";
  currency: "TWD";
  balanceMinor: number;
  createdAt?: string;
};

export type TaiwanTransaction = {
  id: string;
  walletId: string;
  walletName: string;
  amountMinor: number;
  direction: "in" | "out";
  remark?: string | null;
  createdAt?: string;
};

export type TaiwanSummary = {
  totalBalanceMinor: number;
  walletCount: number;
};

export type ModuleSection = {
  id: string;
  title: string;
  href: string;
  description: string;
  walletTypes: WalletType[];
};
