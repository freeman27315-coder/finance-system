import { mockDashboardData } from "@/lib/mock-data";
import { decimalToMinor } from "@/lib/money";
import type { Currency, DashboardData, VendorSummary, WalletBalance, WalletType } from "@/types";

type AssetWalletResponse = {
  id: string | number;
  name: string;
  type: WalletType;
  currency: Currency;
  balance: string | number;
  parent_id?: string | number | null;
  parentId?: string | number | null;
};

type VendorSummaryResponse = {
  payable?: string | number;
  receivable?: string | number;
  net?: string | number;
  payable_cny?: string | number;
  receivable_cny?: string | number;
  net_cny?: string | number;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: {
      accept: "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function normalizeWallet(wallet: AssetWalletResponse): WalletBalance {
  return {
    id: String(wallet.id),
    name: wallet.name,
    type: wallet.type,
    currency: wallet.currency,
    balanceMinor: decimalToMinor(wallet.balance, wallet.currency),
    parentId: wallet.parent_id === undefined ? wallet.parentId?.toString() ?? null : wallet.parent_id?.toString() ?? null
  };
}

function normalizeVendorSummary(summary: VendorSummaryResponse): VendorSummary {
  const payable = summary.payable ?? summary.payable_cny ?? 0;
  const receivable = summary.receivable ?? summary.receivable_cny ?? 0;
  const net = summary.net ?? summary.net_cny ?? 0;

  return {
    payableMinor: decimalToMinor(payable, "CNY"),
    receivableMinor: decimalToMinor(receivable, "CNY"),
    netMinor: decimalToMinor(net, "CNY"),
    currency: "CNY"
  };
}

export async function getDashboardData(): Promise<DashboardData> {
  try {
    const [wallets, vendorSummary] = await Promise.all([
      fetchJson<AssetWalletResponse[]>("/api/wallets/assets"),
      fetchJson<VendorSummaryResponse>("/api/vendors/summary")
    ]);

    return {
      wallets: wallets.map(normalizeWallet),
      vendorSummary: normalizeVendorSummary(vendorSummary)
    };
  } catch {
    return mockDashboardData;
  }
}
