import { mockAssetTransactions, mockDashboardData } from "@/lib/mock-data";
import { decimalToMinor } from "@/lib/money";
import type {
  AssetTransaction,
  Currency,
  DashboardData,
  VendorSummary,
  WalletBalance,
  WalletType
} from "@/types";

type AssetWalletResponse = {
  id: string | number;
  name: string;
  type: WalletType;
  currency: Currency;
  balance: string | number;
  is_group?: boolean;
  isGroup?: boolean;
  children?: AssetWalletResponse[];
  parent_id?: string | number | null;
  parentId?: string | number | null;
  remark?: string | null;
  deleted_at?: string | null;
  deletedAt?: string | null;
};

type VendorSummaryResponse = {
  payable?: string | number;
  receivable?: string | number;
  net?: string | number;
  payable_cny?: string | number;
  receivable_cny?: string | number;
  net_cny?: string | number;
};

type AssetTransactionResponse = {
  id: string | number;
  wallet_id?: string | number;
  walletId?: string | number;
  wallet_name?: string;
  walletName?: string;
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
  currency?: Currency;
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

function normalizeWallet(wallet: AssetWalletResponse, parentId?: string | null): WalletBalance {
  return {
    id: String(wallet.id),
    name: wallet.name,
    type: wallet.type,
    currency: wallet.currency,
    balanceMinor: decimalToMinor(wallet.balance, wallet.currency),
    isGroup: Boolean(wallet.is_group ?? wallet.isGroup ?? false),
    parentId:
      parentId ??
      (wallet.parent_id === undefined ? wallet.parentId?.toString() ?? null : wallet.parent_id?.toString() ?? null),
    remark: wallet.remark ?? null,
    deletedAt: wallet.deleted_at ?? wallet.deletedAt ?? null,
    children: wallet.children?.map((child) => normalizeWallet(child, String(wallet.id))) ?? []
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
      wallets: wallets.map((wallet) => normalizeWallet(wallet)),
      vendorSummary: normalizeVendorSummary(vendorSummary)
    };
  } catch {
    return mockDashboardData;
  }
}

export async function getAssetWallets(): Promise<WalletBalance[]> {
  try {
    const wallets = await fetchJson<AssetWalletResponse[]>("/api/wallets/assets");
    return wallets.map((wallet) => normalizeWallet(wallet));
  } catch {
    return mockDashboardData.wallets.filter((wallet) => wallet.type === "ASSET_RMB" || wallet.type === "ASSET_USDT");
  }
}

function normalizeTransaction(transaction: AssetTransactionResponse, wallet: WalletBalance): AssetTransaction {
  return {
    id: String(transaction.id),
    walletId: String(transaction.wallet_id ?? transaction.walletId ?? wallet.id),
    walletName: transaction.wallet_name ?? transaction.walletName ?? wallet.name,
    amountMinor: decimalToMinor(transaction.amount, transaction.currency ?? wallet.currency),
    direction: transaction.direction,
    remark: transaction.remark,
    createdAt: transaction.created_at ?? transaction.createdAt ?? "",
    currency: transaction.currency ?? wallet.currency
  };
}

export async function getAssetTransactions(wallet: WalletBalance): Promise<AssetTransaction[]> {
  try {
    const transactions = await fetchJson<AssetTransactionResponse[]>(
      `/api/wallets/assets/${wallet.id}/transactions`
    );
    return transactions.map((transaction) => normalizeTransaction(transaction, wallet));
  } catch {
    return mockAssetTransactions[wallet.id] ?? [];
  }
}

async function postJson(path: string, body: unknown) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json"
    },
    body: JSON.stringify(body)
  });

  const text = await response.text();

  if (!response.ok) {
    let message = `${path} returned ${response.status}`;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: string; message?: string; error?: string };
        message = parsed.detail ?? parsed.message ?? parsed.error ?? text;
      } catch {
        message = text;
      }
    }
    throw new Error(message);
  }

  return text ? JSON.parse(text) : null;
}

export function createAssetSubWallet(walletId: string, name: string) {
  return postJson(`/api/wallets/assets/${walletId}/sub`, { name, is_group: false });
}

async function sendJson(path: string, method: "PATCH" | "DELETE", body?: unknown) {
  const response = await fetch(path, {
    method,
    headers: {
      "content-type": "application/json",
      accept: "application/json"
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  });

  const text = await response.text();

  if (!response.ok) {
    let message = `${path} returned ${response.status}`;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: string; message?: string; error?: string };
        message = parsed.detail ?? parsed.message ?? parsed.error ?? text;
      } catch {
        message = text;
      }
    }
    throw new Error(message);
  }

  return text ? JSON.parse(text) : null;
}

export function patchAssetWallet(
  walletId: string,
  payload: { name?: string; remark?: string | null }
) {
  return sendJson(`/api/wallets/assets/${walletId}`, "PATCH", payload);
}

export function deleteAssetWallet(walletId: string) {
  return sendJson(`/api/wallets/assets/${walletId}`, "DELETE");
}

export function creditAssetWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/wallets/assets/${walletId}/credit`, { amount, remark });
}

export function debitAssetWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/wallets/assets/${walletId}/debit`, { amount, remark });
}
