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

export type ModuleSection = {
  id: string;
  title: string;
  href: string;
  description: string;
  walletTypes: WalletType[];
};
