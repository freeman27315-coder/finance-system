import { mockAssetTransactions, mockDashboardData } from "@/lib/mock-data";
import { decimalToMinor } from "@/lib/money";
import type {
  AssetTransaction,
  Currency,
  DashboardData,
  Vendor,
  VendorBill,
  VendorSummary,
  WalletBalance,
  WalletType,
  XboxAccount,
  XboxCountry,
  XboxSummary,
  XboxTransaction,
  TaobaoAccount,
  TaobaoTransaction,
  TaiwanSummary,
  TaiwanTransaction,
  TaiwanWallet
} from "@/types";

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
  vendor_name?: string;
  vendorName?: string;
  direction: "payable" | "receivable";
  amount: string | number;
  status: "pending" | "settled";
  due_date?: string | null;
  dueDate?: string | null;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type XboxAccountResponse = {
  id: string | number;
  name: string;
  country: XboxCountry;
  currency: "USD" | "GBP";
  rmb_cost?: string | number;
  rmbCost?: string | number;
  local_balance?: string | number;
  localBalance?: string | number;
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type XboxSummaryResponse = {
  us_rmb_cost?: string | number;
  usRmbCost?: string | number;
  us_local_balance?: string | number;
  usLocalBalance?: string | number;
  uk_rmb_cost?: string | number;
  ukRmbCost?: string | number;
  uk_local_balance?: string | number;
  ukLocalBalance?: string | number;
};

type XboxTransactionResponse = {
  id: string | number;
  account_id?: string | number;
  accountId?: string | number;
  account_name?: string;
  accountName?: string;
  rmb_amount?: string | number;
  rmbAmount?: string | number;
  local_amount?: string | number;
  localAmount?: string | number;
  type: "recharge" | "consume";
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

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
  wallet_scope?: "unsettled" | "settled";
  walletScope?: "unsettled" | "settled";
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type TaiwanWalletResponse = {
  id: string | number;
  name: string;
  type?: "TAIWAN";
  currency?: "TWD";
  balance: string | number;
  created_at?: string;
  createdAt?: string;
};

type TaiwanSummaryResponse = {
  total_balance?: string | number;
  totalBalance?: string | number;
  wallet_count?: number;
  walletCount?: number;
};

type TaiwanTransactionResponse = {
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

export async function getAssetWallets(): Promise<WalletBalance[]> {
  try {
    const wallets = await fetchJson<AssetWalletResponse[]>("/api/wallets/assets");
    return wallets.map(normalizeWallet);
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

  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }

  return response.json();
}

export function createAssetSubWallet(walletId: string, name: string) {
  return postJson(`/api/wallets/assets/${walletId}/sub`, { name });
}

export function creditAssetWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/wallets/assets/${walletId}/credit`, { amount, remark });
}

export function debitAssetWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/wallets/assets/${walletId}/debit`, { amount, remark });
}

function normalizeVendor(vendor: VendorResponse): Vendor {
  return {
    id: String(vendor.id),
    name: vendor.name,
    remark: vendor.remark,
    createdAt: vendor.created_at ?? vendor.createdAt
  };
}

function normalizeVendorBill(bill: VendorBillResponse, vendor: Vendor): VendorBill {
  return {
    id: String(bill.id),
    vendorId: String(bill.vendor_id ?? bill.vendorId ?? vendor.id),
    vendorName: bill.vendor_name ?? bill.vendorName ?? vendor.name,
    direction: bill.direction,
    amountMinor: decimalToMinor(bill.amount, "CNY"),
    status: bill.status,
    dueDate: bill.due_date ?? bill.dueDate,
    remark: bill.remark,
    createdAt: bill.created_at ?? bill.createdAt,
    currency: "CNY"
  };
}

export async function getVendors(): Promise<Vendor[]> {
  try {
    const vendors = await fetchJson<VendorResponse[]>("/api/vendors");
    return vendors.map(normalizeVendor);
  } catch {
    const { mockVendors } = await import("@/lib/mock-data");
    return mockVendors;
  }
}

export async function getVendorBills(vendor: Vendor): Promise<VendorBill[]> {
  try {
    const bills = await fetchJson<VendorBillResponse[]>(`/api/vendors/${vendor.id}/bills`);
    return bills.map((bill) => normalizeVendorBill(bill, vendor));
  } catch {
    const { mockVendorBills } = await import("@/lib/mock-data");
    return mockVendorBills[vendor.id] ?? [];
  }
}

export function createVendor(name: string, remark: string) {
  return postJson("/api/vendors", { name, remark });
}

export function createVendorBill(
  vendorId: string,
  direction: "payable" | "receivable",
  amount: string,
  dueDate: string,
  remark: string
) {
  return postJson(`/api/vendors/${vendorId}/bills`, {
    direction,
    amount,
    due_date: dueDate || undefined,
    remark
  });
}

export function settleVendorBill(billId: string) {
  return fetch(`/api/vendors/bills/${billId}/settle`, {
    method: "PATCH",
    headers: {
      accept: "application/json"
    }
  }).then((response) => {
    if (!response.ok) {
      throw new Error(`settle returned ${response.status}`);
    }
    return response.json();
  });
}

function normalizeXboxAccount(account: XboxAccountResponse): XboxAccount {
  return {
    id: String(account.id),
    name: account.name,
    country: account.country,
    currency: account.currency,
    rmbCostMinor: decimalToMinor(account.rmb_cost ?? account.rmbCost ?? 0, "CNY"),
    localBalanceMinor: decimalToMinor(account.local_balance ?? account.localBalance ?? 0, account.currency),
    remark: account.remark,
    createdAt: account.created_at ?? account.createdAt
  };
}

function normalizeXboxSummary(summary: XboxSummaryResponse): XboxSummary {
  return {
    usRmbCostMinor: decimalToMinor(summary.us_rmb_cost ?? summary.usRmbCost ?? 0, "CNY"),
    usLocalBalanceMinor: decimalToMinor(summary.us_local_balance ?? summary.usLocalBalance ?? 0, "USD"),
    ukRmbCostMinor: decimalToMinor(summary.uk_rmb_cost ?? summary.ukRmbCost ?? 0, "CNY"),
    ukLocalBalanceMinor: decimalToMinor(summary.uk_local_balance ?? summary.ukLocalBalance ?? 0, "GBP")
  };
}

function normalizeXboxTransaction(transaction: XboxTransactionResponse, account: XboxAccount): XboxTransaction {
  return {
    id: String(transaction.id),
    accountId: String(transaction.account_id ?? transaction.accountId ?? account.id),
    accountName: transaction.account_name ?? transaction.accountName ?? account.name,
    rmbAmountMinor: decimalToMinor(transaction.rmb_amount ?? transaction.rmbAmount ?? 0, "CNY"),
    localAmountMinor: decimalToMinor(transaction.local_amount ?? transaction.localAmount ?? 0, account.currency),
    type: transaction.type,
    remark: transaction.remark,
    createdAt: transaction.created_at ?? transaction.createdAt,
    currency: account.currency
  };
}

export async function getXboxAccounts(): Promise<XboxAccount[]> {
  try {
    const accounts = await fetchJson<XboxAccountResponse[]>("/api/xbox/accounts");
    return accounts.map(normalizeXboxAccount);
  } catch {
    const { mockXboxAccounts } = await import("@/lib/mock-data");
    return mockXboxAccounts;
  }
}

export async function getXboxSummary(): Promise<XboxSummary> {
  try {
    const summary = await fetchJson<XboxSummaryResponse>("/api/xbox/summary");
    return normalizeXboxSummary(summary);
  } catch {
    const { mockXboxSummary } = await import("@/lib/mock-data");
    return mockXboxSummary;
  }
}

export async function getXboxTransactions(account: XboxAccount): Promise<XboxTransaction[]> {
  try {
    const transactions = await fetchJson<XboxTransactionResponse[]>(
      `/api/xbox/accounts/${account.id}/transactions`
    );
    return transactions.map((transaction) => normalizeXboxTransaction(transaction, account));
  } catch {
    const { mockXboxTransactions } = await import("@/lib/mock-data");
    return mockXboxTransactions[account.id] ?? [];
  }
}

export function createXboxAccount(name: string, country: XboxCountry, remark: string) {
  return postJson("/api/xbox/accounts", { name, country, remark });
}

export function rechargeXboxAccount(accountId: string, rmbAmount: string, localAmount: string) {
  return postJson(`/api/xbox/accounts/${accountId}/recharge`, {
    rmb_amount: rmbAmount,
    local_amount: localAmount
  });
}

export function consumeXboxAccount(accountId: string, localAmount: string, remark: string) {
  return postJson(`/api/xbox/accounts/${accountId}/consume`, {
    local_amount: localAmount,
    remark
  });
}

function normalizeTaobaoAccount(account: TaobaoAccountResponse): TaobaoAccount {
  return {
    id: String(account.id),
    name: account.name,
    unsettledWalletId: String(account.unsettled_wallet_id ?? account.unsettledWalletId ?? ""),
    settledWalletId: String(account.settled_wallet_id ?? account.settledWalletId ?? ""),
    unsettledBalanceMinor: decimalToMinor(account.unsettled_balance ?? account.unsettledBalance ?? 0, "CNY"),
    settledBalanceMinor: decimalToMinor(account.settled_balance ?? account.settledBalance ?? 0, "CNY"),
    remark: account.remark,
    createdAt: account.created_at ?? account.createdAt
  };
}

function normalizeTaobaoTransaction(transaction: TaobaoTransactionResponse): TaobaoTransaction {
  return {
    id: String(transaction.id),
    walletId: String(transaction.wallet_id ?? transaction.walletId ?? ""),
    walletScope: transaction.wallet_scope ?? transaction.walletScope ?? "settled",
    amountMinor: decimalToMinor(transaction.amount, "CNY"),
    direction: transaction.direction,
    remark: transaction.remark,
    createdAt: transaction.created_at ?? transaction.createdAt
  };
}

export async function getTaobaoAccounts(): Promise<TaobaoAccount[]> {
  try {
    const accounts = await fetchJson<TaobaoAccountResponse[]>("/api/taobao/accounts");
    return accounts.map(normalizeTaobaoAccount);
  } catch {
    const { mockTaobaoAccounts } = await import("@/lib/mock-data");
    return mockTaobaoAccounts;
  }
}

export async function getTaobaoTransactions(account: TaobaoAccount): Promise<TaobaoTransaction[]> {
  try {
    const transactions = await fetchJson<TaobaoTransactionResponse[]>(
      `/api/taobao/accounts/${account.id}/transactions`
    );
    return transactions.map(normalizeTaobaoTransaction);
  } catch {
    const { mockTaobaoTransactions } = await import("@/lib/mock-data");
    return mockTaobaoTransactions[account.id] ?? [];
  }
}

export function createTaobaoAccount(name: string, remark: string) {
  return postJson("/api/taobao/accounts", { name, remark });
}

export function creditTaobaoUnsettled(accountId: string, amount: string, remark: string) {
  return postJson(`/api/taobao/accounts/${accountId}/unsettled/credit`, { amount, remark });
}

export function creditTaobaoSettled(accountId: string, amount: string, remark: string) {
  return postJson(`/api/taobao/accounts/${accountId}/settled/credit`, { amount, remark });
}

export function debitTaobaoSettled(accountId: string, amount: string, remark: string) {
  return postJson(`/api/taobao/accounts/${accountId}/settled/debit`, { amount, remark });
}

function normalizeTaiwanWallet(wallet: TaiwanWalletResponse): TaiwanWallet {
  return {
    id: String(wallet.id),
    name: wallet.name,
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: decimalToMinor(wallet.balance, "TWD"),
    createdAt: wallet.created_at ?? wallet.createdAt
  };
}

function normalizeTaiwanSummary(summary: TaiwanSummaryResponse): TaiwanSummary {
  return {
    totalBalanceMinor: decimalToMinor(summary.total_balance ?? summary.totalBalance ?? 0, "TWD"),
    walletCount: summary.wallet_count ?? summary.walletCount ?? 0
  };
}

function normalizeTaiwanTransaction(
  transaction: TaiwanTransactionResponse,
  wallet: TaiwanWallet
): TaiwanTransaction {
  return {
    id: String(transaction.id),
    walletId: String(transaction.wallet_id ?? transaction.walletId ?? wallet.id),
    walletName: transaction.wallet_name ?? transaction.walletName ?? wallet.name,
    amountMinor: decimalToMinor(transaction.amount, "TWD"),
    direction: transaction.direction,
    remark: transaction.remark,
    createdAt: transaction.created_at ?? transaction.createdAt
  };
}

export async function getTaiwanWallets(): Promise<TaiwanWallet[]> {
  try {
    const wallets = await fetchJson<TaiwanWalletResponse[]>("/api/taiwan/wallets");
    return wallets.map(normalizeTaiwanWallet);
  } catch {
    const { mockTaiwanWallets } = await import("@/lib/mock-data");
    return mockTaiwanWallets;
  }
}

export async function getTaiwanSummary(): Promise<TaiwanSummary> {
  try {
    const summary = await fetchJson<TaiwanSummaryResponse>("/api/taiwan/summary");
    return normalizeTaiwanSummary(summary);
  } catch {
    const { mockTaiwanSummary } = await import("@/lib/mock-data");
    return mockTaiwanSummary;
  }
}

export async function getTaiwanTransactions(wallet: TaiwanWallet): Promise<TaiwanTransaction[]> {
  try {
    const transactions = await fetchJson<TaiwanTransactionResponse[]>(
      `/api/taiwan/wallets/${wallet.id}/transactions`
    );
    return transactions.map((transaction) => normalizeTaiwanTransaction(transaction, wallet));
  } catch {
    const { mockTaiwanTransactions } = await import("@/lib/mock-data");
    return mockTaiwanTransactions[wallet.id] ?? [];
  }
}

export function creditTaiwanWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/taiwan/wallets/${walletId}/credit`, { amount, remark });
}

export function debitTaiwanWallet(walletId: string, amount: string, remark: string) {
  return postJson(`/api/taiwan/wallets/${walletId}/debit`, { amount, remark });
}
