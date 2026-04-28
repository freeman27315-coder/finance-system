import {
  mockAssetTransactions,
  mockDashboardData,
  mockTaobaoAccounts,
  mockTaobaoTransactions,
  mockVendorBills,
  mockVendors,
  mockXboxAccounts,
  mockXboxSummary,
  mockXboxTransactions
} from "@/lib/mock-data";
import { decimalToMinor } from "@/lib/money";
import type {
  AssetTransaction,
  BillDirection,
  Currency,
  DashboardData,
  TaobaoAccount,
  TaobaoTransaction,
  TaobaoWalletScope,
  Vendor,
  VendorBill,
  VendorSummary,
  WalletBalance,
  WalletType,
  XboxAccount,
  XboxCountry,
  XboxSummary,
  XboxTransaction,
  XboxTransactionType
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

type VendorResponse = {
  id: string | number;
  name: string;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type VendorBillResponse = {
  id: string | number;
  vendor_id?: string | number;
  vendorId?: string | number;
  direction: BillDirection;
  amount: string | number;
  currency?: Currency;
  status: "pending" | "settled";
  due_date?: string | null;
  dueDate?: string | null;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

function normalizeVendor(vendor: VendorResponse): Vendor {
  return {
    id: String(vendor.id),
    name: vendor.name,
    remark: vendor.remark ?? null,
    createdAt: vendor.created_at ?? vendor.createdAt ?? ""
  };
}

function normalizeVendorBill(bill: VendorBillResponse): VendorBill {
  const currency: Currency = bill.currency ?? "CNY";
  return {
    id: String(bill.id),
    vendorId: String(bill.vendor_id ?? bill.vendorId ?? ""),
    direction: bill.direction,
    amountMinor: decimalToMinor(bill.amount, currency),
    currency,
    status: bill.status,
    dueDate: bill.due_date ?? bill.dueDate ?? null,
    remark: bill.remark ?? null,
    createdAt: bill.created_at ?? bill.createdAt ?? ""
  };
}

export async function getVendors(): Promise<Vendor[]> {
  try {
    const data = await fetchJson<VendorResponse[]>("/api/vendors");
    return data.map(normalizeVendor);
  } catch {
    return mockVendors;
  }
}

export async function createVendor(payload: { name: string; remark?: string }): Promise<Vendor> {
  try {
    const data = (await postJson("/api/vendors", payload)) as VendorResponse;
    return normalizeVendor(data);
  } catch (error) {
    throw error instanceof Error ? error : new Error("创建供应商失败");
  }
}

export async function getVendorBills(vendorId: string): Promise<VendorBill[]> {
  try {
    const data = await fetchJson<VendorBillResponse[]>(`/api/vendors/${vendorId}/bills`);
    return data.map((bill) => normalizeVendorBill({ ...bill, vendor_id: bill.vendor_id ?? vendorId }));
  } catch {
    return (mockVendorBills[vendorId] ?? []).map((bill) => ({ ...bill }));
  }
}

export async function createVendorBill(
  vendorId: string,
  payload: { direction: BillDirection; amount: string; dueDate?: string; remark?: string }
): Promise<VendorBill> {
  const body: Record<string, unknown> = {
    direction: payload.direction,
    amount: payload.amount
  };
  if (payload.dueDate) {
    body.due_date = payload.dueDate;
  }
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(`/api/vendors/${vendorId}/bills`, body)) as VendorBillResponse;
  return normalizeVendorBill({ ...data, vendor_id: data.vendor_id ?? vendorId });
}

export async function settleVendorBill(billId: string): Promise<VendorBill> {
  const data = (await sendJson(`/api/vendors/bills/${billId}/settle`, "PATCH")) as VendorBillResponse;
  return normalizeVendorBill(data);
}

type XboxAccountResponse = {
  id: string | number;
  name: string;
  country: string;
  currency: string;
  rmb_cost?: string | number;
  rmbCost?: string | number;
  local_balance?: string | number;
  localBalance?: string | number;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type XboxTransactionResponse = {
  id: string | number;
  account_id?: string | number;
  accountId?: string | number;
  rmb_amount?: string | number;
  rmbAmount?: string | number;
  local_amount?: string | number;
  localAmount?: string | number;
  type: XboxTransactionType;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type XboxSummaryResponse = {
  USD?: { rmb_cost?: string | number; local_balance?: string | number; rmbCost?: string | number; localBalance?: string | number };
  GBP?: { rmb_cost?: string | number; local_balance?: string | number; rmbCost?: string | number; localBalance?: string | number };
};

function normalizeXboxAccount(account: XboxAccountResponse): XboxAccount {
  const country = (account.country === "UK" ? "UK" : "US") as XboxCountry;
  const currency: Currency = country === "US" ? "USD" : "GBP";
  return {
    id: String(account.id),
    name: account.name,
    country,
    currency,
    rmbCostMinor: decimalToMinor(account.rmb_cost ?? account.rmbCost ?? 0, "CNY"),
    localBalanceMinor: decimalToMinor(account.local_balance ?? account.localBalance ?? 0, currency),
    remark: account.remark ?? null,
    createdAt: account.created_at ?? account.createdAt ?? ""
  };
}

function normalizeXboxTransaction(transaction: XboxTransactionResponse, currency: Currency): XboxTransaction {
  return {
    id: String(transaction.id),
    accountId: String(transaction.account_id ?? transaction.accountId ?? ""),
    rmbAmountMinor: decimalToMinor(transaction.rmb_amount ?? transaction.rmbAmount ?? 0, "CNY"),
    localAmountMinor: decimalToMinor(transaction.local_amount ?? transaction.localAmount ?? 0, currency),
    type: transaction.type,
    remark: transaction.remark ?? null,
    createdAt: transaction.created_at ?? transaction.createdAt ?? "",
    currency
  };
}

export async function getXboxAccounts(country?: XboxCountry): Promise<XboxAccount[]> {
  try {
    const path = country ? `/api/xbox/accounts?country=${country}` : "/api/xbox/accounts";
    const data = await fetchJson<XboxAccountResponse[]>(path);
    return data.map(normalizeXboxAccount);
  } catch {
    return country ? mockXboxAccounts.filter((acc) => acc.country === country) : mockXboxAccounts;
  }
}

export async function createXboxAccount(payload: {
  name: string;
  country: XboxCountry;
  remark?: string;
}): Promise<XboxAccount> {
  const body: Record<string, unknown> = {
    name: payload.name,
    country: payload.country
  };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson("/api/xbox/accounts", body)) as XboxAccountResponse;
  return normalizeXboxAccount(data);
}

export async function rechargeXbox(
  accountId: string,
  payload: { rmbAmount: string; localAmount: string; remark?: string }
): Promise<XboxTransaction> {
  const body: Record<string, unknown> = {
    rmb_amount: payload.rmbAmount,
    local_amount: payload.localAmount
  };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(`/api/xbox/accounts/${accountId}/recharge`, body)) as XboxTransactionResponse;
  // currency unknown without account context; default USD-safe normalization happens via currency arg below
  const account = mockXboxAccounts.find((acc) => acc.id === accountId);
  return normalizeXboxTransaction({ ...data, account_id: data.account_id ?? accountId }, account?.currency ?? "USD");
}

export async function consumeXbox(
  accountId: string,
  payload: { localAmount: string; remark?: string }
): Promise<XboxTransaction> {
  const body: Record<string, unknown> = {
    local_amount: payload.localAmount
  };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(`/api/xbox/accounts/${accountId}/consume`, body)) as XboxTransactionResponse;
  const account = mockXboxAccounts.find((acc) => acc.id === accountId);
  return normalizeXboxTransaction({ ...data, account_id: data.account_id ?? accountId }, account?.currency ?? "USD");
}

export async function getXboxTransactions(account: XboxAccount): Promise<XboxTransaction[]> {
  try {
    const data = await fetchJson<XboxTransactionResponse[]>(`/api/xbox/accounts/${account.id}/transactions`);
    return data.map((tx) => normalizeXboxTransaction({ ...tx, account_id: tx.account_id ?? account.id }, account.currency));
  } catch {
    return mockXboxTransactions[account.id] ?? [];
  }
}

export async function getXboxSummary(): Promise<XboxSummary> {
  try {
    const data = await fetchJson<XboxSummaryResponse>("/api/xbox/summary");
    const usd = data.USD ?? {};
    const gbp = data.GBP ?? {};
    // accountCount unknown from summary endpoint — fetch accounts lazily on consumer if needed
    const accounts = await fetchJson<XboxAccountResponse[]>("/api/xbox/accounts").catch(() => [] as XboxAccountResponse[]);
    const usCount = accounts.filter((acc) => acc.country === "US").length;
    const ukCount = accounts.filter((acc) => acc.country === "UK").length;
    return {
      us: {
        rmbCostMinor: decimalToMinor(usd.rmb_cost ?? usd.rmbCost ?? 0, "CNY"),
        localBalanceMinor: decimalToMinor(usd.local_balance ?? usd.localBalance ?? 0, "USD"),
        accountCount: usCount,
        currency: "USD"
      },
      uk: {
        rmbCostMinor: decimalToMinor(gbp.rmb_cost ?? gbp.rmbCost ?? 0, "CNY"),
        localBalanceMinor: decimalToMinor(gbp.local_balance ?? gbp.localBalance ?? 0, "GBP"),
        accountCount: ukCount,
        currency: "GBP"
      }
    };
  } catch {
    return mockXboxSummary;
  }
}

type TaobaoAccountResponse = {
  id: string | number;
  name: string;
  unsettled_wallet_id?: string | number;
  unsettledWalletId?: string | number;
  settled_wallet_id?: string | number;
  settledWalletId?: string | number;
  unsettled_balance?: string | number;
  unsettledBalance?: string | number;
  settled_balance?: string | number;
  settledBalance?: string | number;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type TaobaoTransactionResponse = {
  id: string | number;
  wallet_id?: string | number;
  walletId?: string | number;
  wallet_scope?: string;
  walletScope?: string;
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

function normalizeTaobaoAccount(account: TaobaoAccountResponse): TaobaoAccount {
  return {
    id: String(account.id),
    name: account.name,
    unsettledWalletId: String(account.unsettled_wallet_id ?? account.unsettledWalletId ?? ""),
    settledWalletId: String(account.settled_wallet_id ?? account.settledWalletId ?? ""),
    unsettledBalanceMinor: decimalToMinor(account.unsettled_balance ?? account.unsettledBalance ?? 0, "CNY"),
    settledBalanceMinor: decimalToMinor(account.settled_balance ?? account.settledBalance ?? 0, "CNY"),
    remark: account.remark ?? null,
    createdAt: account.created_at ?? account.createdAt ?? ""
  };
}

function normalizeTaobaoTransaction(transaction: TaobaoTransactionResponse): TaobaoTransaction {
  const scopeRaw = transaction.wallet_scope ?? transaction.walletScope ?? "unsettled";
  const walletScope: TaobaoWalletScope = scopeRaw === "settled" ? "settled" : "unsettled";
  return {
    id: String(transaction.id),
    walletId: String(transaction.wallet_id ?? transaction.walletId ?? ""),
    walletScope,
    amountMinor: decimalToMinor(transaction.amount, "CNY"),
    direction: transaction.direction,
    remark: transaction.remark ?? null,
    createdAt: transaction.created_at ?? transaction.createdAt ?? ""
  };
}

export async function getTaobaoAccounts(): Promise<TaobaoAccount[]> {
  try {
    const data = await fetchJson<TaobaoAccountResponse[]>("/api/taobao/accounts");
    return data.map(normalizeTaobaoAccount);
  } catch {
    return mockTaobaoAccounts;
  }
}

export async function createTaobaoAccount(payload: { name: string; remark?: string }): Promise<TaobaoAccount> {
  const body: Record<string, unknown> = { name: payload.name };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson("/api/taobao/accounts", body)) as TaobaoAccountResponse;
  return normalizeTaobaoAccount(data);
}

export async function creditTaobaoUnsettled(
  accountId: string,
  payload: { amount: string; remark?: string }
): Promise<TaobaoTransaction> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(
    `/api/taobao/accounts/${accountId}/unsettled/credit`,
    body
  )) as TaobaoTransactionResponse;
  return normalizeTaobaoTransaction(data);
}

export async function creditTaobaoSettled(
  accountId: string,
  payload: { amount: string; remark?: string }
): Promise<TaobaoTransaction> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(
    `/api/taobao/accounts/${accountId}/settled/credit`,
    body
  )) as TaobaoTransactionResponse;
  return normalizeTaobaoTransaction(data);
}

export async function debitTaobaoSettled(
  accountId: string,
  payload: { amount: string; remark?: string }
): Promise<TaobaoTransaction> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(
    `/api/taobao/accounts/${accountId}/settled/debit`,
    body
  )) as TaobaoTransactionResponse;
  return normalizeTaobaoTransaction(data);
}

export async function getTaobaoTransactions(accountId: string): Promise<TaobaoTransaction[]> {
  try {
    const data = await fetchJson<TaobaoTransactionResponse[]>(
      `/api/taobao/accounts/${accountId}/transactions`
    );
    return data.map(normalizeTaobaoTransaction);
  } catch {
    return mockTaobaoTransactions[accountId] ?? [];
  }
}

export async function getVendorSummary(): Promise<VendorSummary> {
  try {
    const data = await fetchJson<VendorSummaryResponse>("/api/vendors/summary");
    return normalizeVendorSummary(data);
  } catch {
    return mockDashboardData.vendorSummary;
  }
}
