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

export type ModuleSection = {
  id: string;
  title: string;
  href: string;
  description: string;
  walletTypes: WalletType[];
};
