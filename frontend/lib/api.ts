import {
  mockAssetTransactions,
  mockDashboardData,
  mockTaiwanSummary,
  mockTaiwanTransactions,
  mockTaiwanWallets,
  mockTaobaoOrders,
  mockTaobaoShops,
  mockTaobaoWalletTransactions,
  mockVendors,
  mockVendorTransactions,
  mockXboxAccounts,
  mockXboxSummary,
  mockXboxTransactions
} from "@/lib/mock-data";
import { decimalToMinor } from "@/lib/money";
import type {
  AssetTransaction,
  Currency,
  DashboardData,
  StoreAlipayType,
  TaiwanSummary,
  TaiwanTransaction,
  TaiwanWallet,
  TaobaoFlowReport,
  TaobaoImportReport,
  TaobaoOrder,
  TaobaoOrderPaymentMethod,
  TaobaoOrderStatus,
  TaobaoShop,
  TaobaoShopWallet,
  TaobaoStoreAlipayWallet,
  TaobaoWalletDailySummary,
  TaobaoWalletTransaction,
  Vendor,
  VendorTransaction,
  WalletBalance,
  WalletType,
  XboxAccount,
  XboxAccountAuditLog,
  XboxAccountStatus,
  XboxCountry,
  XboxOrder,
  XboxOrderStatus,
  XboxPoolOptionGroup,
  XboxSaleCurrency,
  XboxSaleRecord,
  XboxSummary,
  XboxTransaction,
  XboxTransactionType,
  XboxWalletMethod
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

export async function getDashboardData(): Promise<DashboardData> {
  try {
    const wallets = await fetchJson<AssetWalletResponse[]>("/api/wallets/assets");
    return {
      wallets: wallets.map((wallet) => normalizeWallet(wallet))
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

async function sendJson(path: string, method: "PATCH" | "DELETE" | "PUT", body?: unknown) {
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
  walletId?: string | number;
  wallet_id?: string | number;
  balance?: string | number;
  created_at?: string;
  createdAt?: string;
};

type VendorTransactionResponse = {
  id: string | number;
  walletId?: string | number;
  wallet_id?: string | number;
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  createdAt?: string;
  created_at?: string;
};

function normalizeVendor(vendor: VendorResponse): Vendor {
  return {
    id: String(vendor.id),
    name: vendor.name,
    remark: vendor.remark ?? null,
    walletId: String(vendor.walletId ?? vendor.wallet_id ?? ""),
    balanceMinor: decimalToMinor(vendor.balance ?? 0, "CNY"),
    createdAt: vendor.created_at ?? vendor.createdAt ?? ""
  };
}

function normalizeVendorTransaction(tx: VendorTransactionResponse): VendorTransaction {
  return {
    id: String(tx.id),
    walletId: String(tx.walletId ?? tx.wallet_id ?? ""),
    amountMinor: decimalToMinor(tx.amount, "CNY"),
    direction: tx.direction,
    remark: tx.remark ?? null,
    createdAt: tx.createdAt ?? tx.created_at ?? ""
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
  const data = (await postJson("/api/vendors", payload)) as VendorResponse;
  return normalizeVendor(data);
}

export async function getVendorTransactions(vendorId: string): Promise<VendorTransaction[]> {
  try {
    const data = await fetchJson<VendorTransactionResponse[]>(`/api/vendors/${vendorId}/transactions`);
    return data.map(normalizeVendorTransaction);
  } catch {
    return (mockVendorTransactions[vendorId] ?? []).map((tx) => ({ ...tx }));
  }
}

export async function payVendor(
  vendorId: string,
  payload: { fromWalletId: string; amount: string; exchangeRate?: string; remark?: string }
): Promise<unknown> {
  const body: Record<string, unknown> = {
    from_wallet_id: Number(payload.fromWalletId),
    amount: payload.amount
  };
  if (payload.exchangeRate) {
    body.exchange_rate = payload.exchangeRate;
  }
  if (payload.remark) {
    body.remark = payload.remark;
  }
  return postJson(`/api/vendors/${vendorId}/payment`, body);
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
  // PR #103 新字段
  account_no?: string | null;
  accountNo?: string | null;
  login_email?: string | null;
  loginEmail?: string | null;
  has_password?: boolean;
  hasPassword?: boolean;
  exchange_rate?: string | number | null;
  exchangeRate?: string | number | null;
  status?: string;
  status_message?: string | null;
  statusMessage?: string | null;
  last_synced_at?: string | null;
  lastSyncedAt?: string | null;
};

type XboxAccountAuditLogResponse = {
  id: string | number;
  account_id?: string | number;
  accountId?: string | number;
  action: string;
  detail?: string | null;
  operator?: string | null;
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
  const exchangeRateRaw = account.exchange_rate ?? account.exchangeRate ?? null;
  return {
    id: String(account.id),
    name: account.name,
    country,
    currency,
    rmbCostMinor: decimalToMinor(account.rmb_cost ?? account.rmbCost ?? 0, "CNY"),
    localBalanceMinor: decimalToMinor(account.local_balance ?? account.localBalance ?? 0, currency),
    remark: account.remark ?? null,
    createdAt: account.created_at ?? account.createdAt ?? "",
    accountNo: account.account_no ?? account.accountNo ?? null,
    loginEmail: account.login_email ?? account.loginEmail ?? null,
    hasPassword: Boolean(account.has_password ?? account.hasPassword ?? false),
    exchangeRate:
      exchangeRateRaw == null || exchangeRateRaw === ""
        ? null
        : Number(exchangeRateRaw),
    status: ((account.status as XboxAccount["status"]) ?? "active"),
    statusMessage: account.status_message ?? account.statusMessage ?? null,
    lastSyncedAt: account.last_synced_at ?? account.lastSyncedAt ?? null
  };
}

function normalizeXboxAuditLog(log: XboxAccountAuditLogResponse): XboxAccountAuditLog {
  return {
    id: String(log.id),
    accountId: String(log.account_id ?? log.accountId ?? ""),
    action: (log.action as XboxAccountAuditLog["action"]) ?? "updated",
    detail: log.detail ?? null,
    operator: log.operator ?? null,
    createdAt: log.created_at ?? log.createdAt ?? ""
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
  accountNo?: string;
  loginEmail?: string;
  password?: string;
  exchangeRate?: string;
  status?: XboxAccountStatus;
  statusMessage?: string;
}): Promise<XboxAccount> {
  const body: Record<string, unknown> = {
    name: payload.name,
    country: payload.country
  };
  if (payload.remark) body.remark = payload.remark;
  if (payload.accountNo) body.accountNo = payload.accountNo;
  if (payload.loginEmail) body.loginEmail = payload.loginEmail;
  if (payload.password) body.password = payload.password;
  if (payload.exchangeRate) body.exchangeRate = payload.exchangeRate;
  if (payload.status) body.status = payload.status;
  if (payload.statusMessage) body.statusMessage = payload.statusMessage;
  const data = (await postJson("/api/xbox/accounts", body)) as XboxAccountResponse;
  return normalizeXboxAccount(data);
}

export async function updateXboxAccount(
  accountId: string,
  payload: {
    name?: string;
    accountNo?: string;
    loginEmail?: string;
    exchangeRate?: string;
    rmbCost?: string;
    localBalance?: string;
    remark?: string;
  }
): Promise<XboxAccount> {
  const body: Record<string, unknown> = {};
  if (payload.name !== undefined) body.name = payload.name;
  if (payload.accountNo !== undefined) body.accountNo = payload.accountNo;
  if (payload.loginEmail !== undefined) body.loginEmail = payload.loginEmail;
  if (payload.exchangeRate !== undefined) body.exchangeRate = payload.exchangeRate;
  if (payload.rmbCost !== undefined) body.rmbCost = payload.rmbCost;
  if (payload.localBalance !== undefined) body.localBalance = payload.localBalance;
  if (payload.remark !== undefined) body.remark = payload.remark;
  const data = (await sendJson(`/api/xbox/accounts/${accountId}`, "PATCH", body)) as XboxAccountResponse;
  return normalizeXboxAccount(data);
}

export async function changeXboxAccountPassword(
  accountId: string,
  password: string
): Promise<XboxAccount> {
  const data = (await sendJson(`/api/xbox/accounts/${accountId}/password`, "PATCH", {
    password
  })) as XboxAccountResponse;
  return normalizeXboxAccount(data);
}

export async function changeXboxAccountStatus(
  accountId: string,
  status: XboxAccountStatus,
  statusMessage?: string
): Promise<XboxAccount> {
  const body: Record<string, unknown> = { status };
  if (statusMessage !== undefined) body.statusMessage = statusMessage;
  const data = (await sendJson(`/api/xbox/accounts/${accountId}/status`, "PATCH", body)) as XboxAccountResponse;
  return normalizeXboxAccount(data);
}

export async function getXboxAccountAuditLogs(
  accountId: string
): Promise<XboxAccountAuditLog[]> {
  try {
    const data = await fetchJson<XboxAccountAuditLogResponse[]>(
      `/api/xbox/accounts/${accountId}/audit-logs`
    );
    return data.map(normalizeXboxAuditLog);
  } catch {
    return [];
  }
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

// ===================================================================
// PR #110/#112 P0.2 — XBOX 订单 / 销售记录 / 钱包设置
// ===================================================================

type XboxOrderResponse = {
  id: string | number;
  accountId?: string | number;
  account_id?: string | number;
  orderNo?: string;
  order_no?: string;
  amountLocal?: string | number;
  amount_local?: string | number;
  currencyLocal?: string;
  currency_local?: string;
  exchangeRate?: string | number | null;
  exchange_rate?: string | number | null;
  rmbCost?: string | number;
  rmb_cost?: string | number;
  orderAt?: string;
  order_at?: string;
  status: string;
  saleDate?: string | null;
  sale_date?: string | null;
  productName?: string | null;
  product_name?: string | null;
  operatorName?: string | null;
  operator_name?: string | null;
  salePrice?: string | number | null;
  sale_price?: string | number | null;
  saleCurrency?: string | null;
  sale_currency?: string | null;
  walletMethodId?: string | number | null;
  wallet_method_id?: string | number | null;
  walletItemId?: string | number | null;
  wallet_item_id?: string | number | null;
  saleRecordId?: string | number | null;
  sale_record_id?: string | number | null;
  createdAt?: string;
  created_at?: string;
  lastUpdatedAt?: string;
  last_updated_at?: string;
};

type XboxSaleRecordResponse = {
  id: string | number;
  accountId?: string | number;
  account_id?: string | number;
  saleDate?: string;
  sale_date?: string;
  productName?: string;
  product_name?: string;
  operatorName?: string;
  operator_name?: string;
  salePrice?: string | number;
  sale_price?: string | number;
  saleCurrency?: string;
  sale_currency?: string;
  walletMethodId?: string | number;
  wallet_method_id?: string | number;
  walletItemId?: string | number;
  wallet_item_id?: string | number;
  walletItemLabel?: string;
  wallet_item_label?: string;
  walletPoolId?: string | number;
  wallet_pool_id?: string | number;
  bookkeepingTxId?: string | number | null;
  bookkeeping_tx_id?: string | number | null;
  orderIds?: (string | number)[];
  order_ids?: (string | number)[];
  createdAt?: string;
  created_at?: string;
  lastUpdatedAt?: string;
  last_updated_at?: string;
};

type XboxWalletMethodResponse = {
  id: string | number;
  code: string;
  label: string;
  isActive?: boolean;
  is_active?: boolean;
  items: {
    id: string | number;
    code: string;
    label: string;
    walletPoolId?: string | number;
    wallet_pool_id?: string | number;
    isActive?: boolean;
    is_active?: boolean;
  }[];
};

function _normalizeOrder(o: XboxOrderResponse): XboxOrder {
  const localCurrency = (o.currencyLocal ?? o.currency_local ?? "USD") as
    | "USD"
    | "GBP";
  const saleCurrency = (o.saleCurrency ?? o.sale_currency ?? null) as
    | XboxSaleCurrency
    | null;
  const exchangeRateRaw = o.exchangeRate ?? o.exchange_rate ?? null;
  const salePriceRaw = o.salePrice ?? o.sale_price ?? null;
  return {
    id: String(o.id),
    accountId: String(o.accountId ?? o.account_id ?? ""),
    orderNo: o.orderNo ?? o.order_no ?? "",
    amountLocal: decimalToMinor(o.amountLocal ?? o.amount_local ?? 0, localCurrency),
    currencyLocal: localCurrency,
    exchangeRate:
      exchangeRateRaw == null || exchangeRateRaw === ""
        ? null
        : Number(exchangeRateRaw),
    rmbCost: decimalToMinor(o.rmbCost ?? o.rmb_cost ?? 0, "CNY"),
    orderAt: o.orderAt ?? o.order_at ?? "",
    status: (o.status as XboxOrderStatus) ?? "pending_complete",
    saleDate: o.saleDate ?? o.sale_date ?? null,
    productName: o.productName ?? o.product_name ?? null,
    operatorName: o.operatorName ?? o.operator_name ?? null,
    salePrice:
      salePriceRaw == null
        ? null
        : decimalToMinor(salePriceRaw, saleCurrency ?? "CNY"),
    saleCurrency,
    walletMethodId:
      o.walletMethodId == null && o.wallet_method_id == null
        ? null
        : String(o.walletMethodId ?? o.wallet_method_id),
    walletItemId:
      o.walletItemId == null && o.wallet_item_id == null
        ? null
        : String(o.walletItemId ?? o.wallet_item_id),
    saleRecordId:
      o.saleRecordId == null && o.sale_record_id == null
        ? null
        : String(o.saleRecordId ?? o.sale_record_id),
    createdAt: o.createdAt ?? o.created_at ?? "",
    lastUpdatedAt: o.lastUpdatedAt ?? o.last_updated_at ?? ""
  };
}

function _normalizeSaleRecord(r: XboxSaleRecordResponse): XboxSaleRecord {
  const currency = (r.saleCurrency ?? r.sale_currency ?? "CNY") as XboxSaleCurrency;
  return {
    id: String(r.id),
    accountId: String(r.accountId ?? r.account_id ?? ""),
    saleDate: r.saleDate ?? r.sale_date ?? "",
    productName: r.productName ?? r.product_name ?? "",
    operatorName: r.operatorName ?? r.operator_name ?? "",
    salePrice: decimalToMinor(r.salePrice ?? r.sale_price ?? 0, currency),
    saleCurrency: currency,
    walletMethodId: String(r.walletMethodId ?? r.wallet_method_id ?? ""),
    walletItemId: String(r.walletItemId ?? r.wallet_item_id ?? ""),
    walletItemLabel: r.walletItemLabel ?? r.wallet_item_label ?? "",
    walletPoolId: String(r.walletPoolId ?? r.wallet_pool_id ?? ""),
    bookkeepingTxId:
      r.bookkeepingTxId == null && r.bookkeeping_tx_id == null
        ? null
        : String(r.bookkeepingTxId ?? r.bookkeeping_tx_id),
    orderIds: (r.orderIds ?? r.order_ids ?? []).map((x) => String(x)),
    createdAt: r.createdAt ?? r.created_at ?? "",
    lastUpdatedAt: r.lastUpdatedAt ?? r.last_updated_at ?? ""
  };
}

function _normalizeWalletMethod(m: XboxWalletMethodResponse): XboxWalletMethod {
  return {
    id: String(m.id),
    code: m.code,
    label: m.label,
    isActive: Boolean(m.isActive ?? m.is_active ?? true),
    items: (m.items ?? []).map((it) => ({
      id: String(it.id),
      code: it.code,
      label: it.label,
      walletPoolId: String(it.walletPoolId ?? it.wallet_pool_id ?? ""),
      isActive: Boolean(it.isActive ?? it.is_active ?? true)
    }))
  };
}

export async function getXboxOrders(filter?: {
  accountId?: string;
  status?: XboxOrderStatus;
  from?: string; // YYYY-MM-DD
  to?: string;
}): Promise<XboxOrder[]> {
  const qs = new URLSearchParams();
  if (filter?.accountId) qs.set("accountId", filter.accountId);
  if (filter?.status) qs.set("status", filter.status);
  if (filter?.from) qs.set("from", filter.from);
  if (filter?.to) qs.set("to", filter.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  try {
    const data = await fetchJson<XboxOrderResponse[]>(`/api/xbox/orders${suffix}`);
    return data.map(_normalizeOrder);
  } catch {
    return [];
  }
}

export async function createXboxOrder(payload: {
  accountId: string;
  orderNo: string;
  amountLocal: string;
  currencyLocal: string;
  orderAt: string;
  exchangeRate?: string;
}): Promise<XboxOrder> {
  const body: Record<string, unknown> = {
    accountId: payload.accountId,
    orderNo: payload.orderNo,
    amountLocal: payload.amountLocal,
    currencyLocal: payload.currencyLocal,
    orderAt: payload.orderAt
  };
  if (payload.exchangeRate) body.exchangeRate = payload.exchangeRate;
  const data = (await postJson("/api/xbox/orders", body)) as XboxOrderResponse;
  return _normalizeOrder(data);
}

export async function patchXboxOrder(
  orderId: string,
  payload: {
    saleDate?: string;
    productName?: string;
    operatorName?: string;
    salePrice?: string;
    saleCurrency?: XboxSaleCurrency;
    walletMethodId?: string;
    walletItemId?: string;
  }
): Promise<XboxOrder> {
  const body: Record<string, unknown> = {};
  if (payload.saleDate !== undefined) body.saleDate = payload.saleDate;
  if (payload.productName !== undefined) body.productName = payload.productName;
  if (payload.operatorName !== undefined) body.operatorName = payload.operatorName;
  if (payload.salePrice !== undefined) body.salePrice = payload.salePrice;
  if (payload.saleCurrency !== undefined) body.saleCurrency = payload.saleCurrency;
  if (payload.walletMethodId !== undefined) body.walletMethodId = payload.walletMethodId;
  if (payload.walletItemId !== undefined) body.walletItemId = payload.walletItemId;
  const data = (await sendJson(`/api/xbox/orders/${orderId}`, "PATCH", body)) as XboxOrderResponse;
  return _normalizeOrder(data);
}

export async function getXboxSaleRecords(filter?: {
  accountId?: string;
  from?: string;
  to?: string;
}): Promise<XboxSaleRecord[]> {
  const qs = new URLSearchParams();
  if (filter?.accountId) qs.set("accountId", filter.accountId);
  if (filter?.from) qs.set("from", filter.from);
  if (filter?.to) qs.set("to", filter.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  try {
    const data = await fetchJson<XboxSaleRecordResponse[]>(`/api/xbox/sale-records${suffix}`);
    return data.map(_normalizeSaleRecord);
  } catch {
    return [];
  }
}

export type XboxSalesSummary = {
  totalByCurrency: { currency: string; total: string; count: number }[];
  totalByMethod: { methodLabel: string; currency: string; total: string; count: number }[];
  totalByItem: { itemLabel: string; currency: string; total: string; count: number }[];
  saleRecordCount: number;
  orderCount: number;
};

export async function getXboxSalesSummary(filter?: {
  from?: string;
  to?: string;
}): Promise<XboxSalesSummary> {
  const qs = new URLSearchParams();
  if (filter?.from) qs.set("from", filter.from);
  if (filter?.to) qs.set("to", filter.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  try {
    return await fetchJson<XboxSalesSummary>(`/api/xbox/sales-summary${suffix}`);
  } catch {
    return {
      totalByCurrency: [],
      totalByMethod: [],
      totalByItem: [],
      saleRecordCount: 0,
      orderCount: 0
    };
  }
}

export function exportXboxSaleRecordsUrl(filter?: { from?: string; to?: string; accountId?: string }): string {
  const qs = new URLSearchParams();
  if (filter?.from) qs.set("from", filter.from);
  if (filter?.to) qs.set("to", filter.to);
  if (filter?.accountId) qs.set("accountId", filter.accountId);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return `/api/xbox/sale-records/export${suffix}`;
}

// 对账：映射 CRUD + 报告
import type { XboxReconcileMapping, XboxReconcileReportRow } from "@/types";

type XboxReconcileMappingResponse = {
  id: string | number;
  theoreticalWalletId?: string | number;
  theoretical_wallet_id?: string | number;
  actualWalletId?: string | number;
  actual_wallet_id?: string | number;
  createdAt?: string;
  created_at?: string;
};

function _normalizeMapping(m: XboxReconcileMappingResponse): XboxReconcileMapping {
  return {
    id: String(m.id),
    theoreticalWalletId: String(m.theoreticalWalletId ?? m.theoretical_wallet_id ?? ""),
    actualWalletId: String(m.actualWalletId ?? m.actual_wallet_id ?? ""),
    createdAt: m.createdAt ?? m.created_at ?? ""
  };
}

export async function getXboxReconcileMappings(): Promise<XboxReconcileMapping[]> {
  try {
    const data = await fetchJson<XboxReconcileMappingResponse[]>(
      "/api/xbox/reconcile-mappings"
    );
    return data.map(_normalizeMapping);
  } catch {
    return [];
  }
}

export async function createXboxReconcileMapping(payload: {
  theoreticalWalletId: string;
  actualWalletId: string;
}): Promise<XboxReconcileMapping> {
  const data = (await postJson("/api/xbox/reconcile-mappings", payload)) as XboxReconcileMappingResponse;
  return _normalizeMapping(data);
}

export async function deleteXboxReconcileMapping(mappingId: string): Promise<void> {
  await sendJson(`/api/xbox/reconcile-mappings/${mappingId}`, "DELETE");
}

export async function getXboxReconcileReport(date: string): Promise<XboxReconcileReportRow[]> {
  try {
    return await fetchJson<XboxReconcileReportRow[]>(
      `/api/xbox/reconcile?date=${date}`
    );
  } catch {
    return [];
  }
}

export async function patchXboxSaleRecord(
  recordId: string,
  payload: {
    saleDate?: string;
    productName?: string;
    operatorName?: string;
    salePrice?: string;
    saleCurrency?: XboxSaleCurrency;
    walletMethodId?: string;
    walletItemId?: string;
    walletItemLabel?: string;
    walletPoolId?: string;
  }
): Promise<XboxSaleRecord> {
  const body: Record<string, unknown> = {};
  for (const k of Object.keys(payload) as (keyof typeof payload)[]) {
    const v = payload[k];
    if (v !== undefined) body[k] = v;
  }
  const data = (await sendJson(
    `/api/xbox/sale-records/${recordId}`,
    "PATCH",
    body
  )) as XboxSaleRecordResponse;
  return _normalizeSaleRecord(data);
}

export async function getXboxWalletSettings(onlyActive = true): Promise<XboxWalletMethod[]> {
  try {
    const data = await fetchJson<XboxWalletMethodResponse[]>(
      `/api/xbox/wallet-settings?onlyActive=${onlyActive}`
    );
    return data.map(_normalizeWalletMethod);
  } catch {
    return [];
  }
}

type XboxPoolOptionGroupResponse = {
  groupCode?: string;
  group_code?: string;
  groupLabel?: string;
  group_label?: string;
  wallets: {
    id: string | number;
    name: string;
    currency: string;
    fullPath?: string;
    full_path?: string;
  }[];
};

export async function getXboxWalletPoolOptions(
  options?: { xboxOnly?: boolean; includeGroups?: boolean }
): Promise<XboxPoolOptionGroup[]> {
  const xboxOnly = options?.xboxOnly ?? true;
  const includeGroups = options?.includeGroups ?? false;
  try {
    const data = await fetchJson<XboxPoolOptionGroupResponse[]>(
      `/api/xbox/wallet-pool-options?xboxOnly=${xboxOnly}&includeGroups=${includeGroups}`
    );
    return data.map((g) => ({
      groupCode: g.groupCode ?? g.group_code ?? "",
      groupLabel: g.groupLabel ?? g.group_label ?? "",
      wallets: (g.wallets ?? []).map((w) => ({
        id: String(w.id),
        name: w.name,
        currency: w.currency,
        fullPath: w.fullPath ?? w.full_path ?? w.name
      }))
    }));
  } catch {
    return [];
  }
}

type XboxChangeLogResponse = {
  id: string | number;
  entityType?: string;
  entity_type?: string;
  entityId?: string | number;
  entity_id?: string | number;
  action: string;
  detail?: string | null;
  operator?: string | null;
  createdAt?: string;
  created_at?: string;
};

function _normalizeChangeLog(log: XboxChangeLogResponse) {
  return {
    id: String(log.id),
    entityType: ((log.entityType ?? log.entity_type) as "order" | "sale_record") ?? "order",
    entityId: String(log.entityId ?? log.entity_id ?? ""),
    action: log.action as "created" | "updated" | "completed" | "merged" | "wallet_pool_changed",
    detail: log.detail ?? null,
    operator: log.operator ?? null,
    createdAt: log.createdAt ?? log.created_at ?? ""
  };
}

export async function getXboxOrderChangeLogs(orderId: string) {
  try {
    const data = await fetchJson<XboxChangeLogResponse[]>(
      `/api/xbox/orders/${orderId}/change-logs`
    );
    return data.map(_normalizeChangeLog);
  } catch {
    return [];
  }
}

export async function getXboxSaleRecordChangeLogs(recordId: string) {
  try {
    const data = await fetchJson<XboxChangeLogResponse[]>(
      `/api/xbox/sale-records/${recordId}/change-logs`
    );
    return data.map(_normalizeChangeLog);
  } catch {
    return [];
  }
}

export async function pushXboxWalletSettings(
  methods: {
    code: string;
    label: string;
    items: { code: string; label: string; walletPoolId: string; isActive?: boolean }[];
  }[]
): Promise<{ methodsUpserted: number; itemsUpserted: number; itemsDisabled: number }> {
  const data = (await sendJson(`/api/xbox/wallet-settings`, "PUT", methods)) as {
    methods_upserted?: number;
    items_upserted?: number;
    items_disabled?: number;
    methodsUpserted?: number;
    itemsUpserted?: number;
    itemsDisabled?: number;
  };
  return {
    methodsUpserted: Number(data.methodsUpserted ?? data.methods_upserted ?? 0),
    itemsUpserted: Number(data.itemsUpserted ?? data.items_upserted ?? 0),
    itemsDisabled: Number(data.itemsDisabled ?? data.items_disabled ?? 0)
  };
}


// ---------------------------------------------------------------------------
// Taobao（PR #65/#67/#69/#73）—— 3 店铺 × 5 钱包 + storeAlipayWallet 必填带 type + Excel 导入
// ---------------------------------------------------------------------------

type TaobaoShopWalletResponse = {
  id: string | number;
  name: string;
  balance: string | number;
  type?: string;
};

type TaobaoShopResponse = {
  id: string | number;
  name: string;
  storeAlipayWallet?: TaobaoShopWalletResponse;
  store_alipay_wallet?: TaobaoShopWalletResponse;
  unconfirmedAlipay?: TaobaoShopWalletResponse;
  unconfirmed_alipay?: TaobaoShopWalletResponse;
  unconfirmedWechat?: TaobaoShopWalletResponse;
  unconfirmed_wechat?: TaobaoShopWalletResponse;
  aggregatorFrozen?: TaobaoShopWalletResponse;
  aggregator_frozen?: TaobaoShopWalletResponse;
  aggregatorAvailable?: TaobaoShopWalletResponse;
  aggregator_available?: TaobaoShopWalletResponse;
  bankCard?: TaobaoShopWalletResponse;
  bank_card?: TaobaoShopWalletResponse;
  // PR #81：实时聚合"待解冻"金额 + 笔数（Decimal 字符串 / 整数）
  aggregatorMaturedAmount?: string | number;
  aggregator_matured_amount?: string | number;
  aggregatorMaturedCount?: number;
  aggregator_matured_count?: number;
  remark?: string | null;
  createdAt?: string;
  created_at?: string;
};

type TaobaoOrderResponse = {
  id: string | number;
  orderNumber?: string;
  order_number?: string;
  paymentMethod?: string;
  payment_method?: string;
  amount: string | number;
  status: string;
  bookkeepingWalletId?: string | number | null;
  bookkeeping_wallet_id?: string | number | null;
  bookkeepingTxId?: string | number | null;
  bookkeeping_tx_id?: string | number | null;
  shippedAt?: string | null;
  shipped_at?: string | null;
  receivedAt?: string | null;
  received_at?: string | null;
  lastSyncedAt?: string;
  last_synced_at?: string;
  recordedAt?: string;
  recorded_at?: string;
};

type TaobaoWalletTransactionResponse = {
  id: string | number;
  walletId?: string | number;
  wallet_id?: string | number;
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  createdAt?: string;
  created_at?: string;
  matureAt?: string | null;
  mature_at?: string | null;
};

type TaobaoImportReportResponse = {
  shopName?: string;
  shop_name?: string;
  totalRowsParsed?: number;
  total_rows_parsed?: number;
  createdOrders?: number;
  created_orders?: number;
  statusChangedOrders?: number;
  status_changed_orders?: number;
  closedReverted?: number;
  closed_reverted?: number;
  skippedNoChange?: number;
  skipped_no_change?: number;
  skippedUnpaidOrUnshipped?: number;
  skipped_unpaid_or_unshipped?: number;
  skippedUnknownPayment?: number;
  skipped_unknown_payment?: number;
  // PR #85：自动结算字段
  autoReleasedAmount?: string | number;
  auto_released_amount?: string | number;
  autoReleasedCount?: number;
  auto_released_count?: number;
  totalFeeAmount?: string | number;
  total_fee_amount?: string | number;
  errors?: string[];
};

type TaobaoFlowReportResponse = {
  amount: string | number;
  fromWalletId?: string | number;
  from_wallet_id?: string | number;
  fromWalletBalance?: string | number;
  from_wallet_balance?: string | number;
  toWalletId?: string | number;
  to_wallet_id?: string | number;
  toWalletBalance?: string | number;
  to_wallet_balance?: string | number;
  remark: string;
};

function normalizeTaobaoShopWallet(wallet: TaobaoShopWalletResponse): TaobaoShopWallet {
  return {
    id: String(wallet.id),
    name: wallet.name,
    balanceMinor: decimalToMinor(wallet.balance, "CNY")
  };
}

function normalizeStoreAlipayType(rawType: string | undefined): StoreAlipayType {
  // 后端返回大写 WalletType 枚举值，淘宝店铺支付宝只可能是 ASSET_RMB（丙火/小小）或 TAOBAO（兔仔）
  const upper = (rawType ?? "").toUpperCase();
  return upper === "TAOBAO" ? "TAOBAO" : "ASSET_RMB";
}

function normalizeStoreAlipayWallet(wallet: TaobaoShopWalletResponse): TaobaoStoreAlipayWallet {
  return {
    ...normalizeTaobaoShopWallet(wallet),
    type: normalizeStoreAlipayType(wallet.type)
  };
}

function normalizeTaobaoShop(shop: TaobaoShopResponse): TaobaoShop {
  const storeAlipayWallet = shop.storeAlipayWallet ?? shop.store_alipay_wallet;
  const unconfirmedAlipay = shop.unconfirmedAlipay ?? shop.unconfirmed_alipay;
  const unconfirmedWechat = shop.unconfirmedWechat ?? shop.unconfirmed_wechat;
  const aggregatorFrozen = shop.aggregatorFrozen ?? shop.aggregator_frozen;
  const aggregatorAvailable = shop.aggregatorAvailable ?? shop.aggregator_available;
  const bankCard = shop.bankCard ?? shop.bank_card;

  if (
    !storeAlipayWallet ||
    !unconfirmedAlipay ||
    !unconfirmedWechat ||
    !aggregatorFrozen ||
    !aggregatorAvailable ||
    !bankCard
  ) {
    throw new Error("淘宝店铺响应字段不完整");
  }

  const maturedAmountRaw = shop.aggregatorMaturedAmount ?? shop.aggregator_matured_amount ?? 0;
  const maturedCountRaw = shop.aggregatorMaturedCount ?? shop.aggregator_matured_count ?? 0;

  return {
    id: String(shop.id),
    name: shop.name,
    storeAlipayWallet: normalizeStoreAlipayWallet(storeAlipayWallet),
    unconfirmedAlipay: normalizeTaobaoShopWallet(unconfirmedAlipay),
    unconfirmedWechat: normalizeTaobaoShopWallet(unconfirmedWechat),
    aggregatorFrozen: normalizeTaobaoShopWallet(aggregatorFrozen),
    aggregatorAvailable: normalizeTaobaoShopWallet(aggregatorAvailable),
    bankCard: normalizeTaobaoShopWallet(bankCard),
    aggregatorMaturedAmountMinor: decimalToMinor(maturedAmountRaw, "CNY"),
    aggregatorMaturedCount: Number(maturedCountRaw) || 0,
    remark: shop.remark ?? null,
    createdAt: shop.createdAt ?? shop.created_at ?? ""
  };
}

function normalizeTaobaoOrder(order: TaobaoOrderResponse): TaobaoOrder {
  const paymentMethod = (order.paymentMethod ?? order.payment_method ?? "alipay") as TaobaoOrderPaymentMethod;
  const status = order.status as TaobaoOrderStatus;
  const walletId = order.bookkeepingWalletId ?? order.bookkeeping_wallet_id;
  const txId = order.bookkeepingTxId ?? order.bookkeeping_tx_id;
  return {
    id: String(order.id),
    orderNumber: order.orderNumber ?? order.order_number ?? "",
    paymentMethod,
    amountMinor: decimalToMinor(order.amount, "CNY"),
    status,
    bookkeepingWalletId: walletId == null ? null : String(walletId),
    bookkeepingTxId: txId == null ? null : String(txId),
    shippedAt: order.shippedAt ?? order.shipped_at ?? null,
    receivedAt: order.receivedAt ?? order.received_at ?? null,
    lastSyncedAt: order.lastSyncedAt ?? order.last_synced_at ?? "",
    recordedAt: order.recordedAt ?? order.recorded_at ?? ""
  };
}

function normalizeTaobaoWalletTransaction(tx: TaobaoWalletTransactionResponse): TaobaoWalletTransaction {
  return {
    id: String(tx.id),
    walletId: String(tx.walletId ?? tx.wallet_id ?? ""),
    amountMinor: decimalToMinor(tx.amount, "CNY"),
    direction: tx.direction,
    remark: tx.remark ?? null,
    createdAt: tx.createdAt ?? tx.created_at ?? "",
    matureAt: tx.matureAt ?? tx.mature_at ?? null
  };
}

type TaobaoWalletDailySummaryResponse = {
  date: string;
  inAmount?: string | number;
  in_amount?: string | number;
  outAmount?: string | number;
  out_amount?: string | number;
  netAmount?: string | number;
  net_amount?: string | number;
  count: number;
};

function normalizeTaobaoWalletDailySummary(
  row: TaobaoWalletDailySummaryResponse
): TaobaoWalletDailySummary {
  return {
    date: row.date,
    inAmountMinor: decimalToMinor(row.inAmount ?? row.in_amount ?? "0", "CNY"),
    outAmountMinor: decimalToMinor(row.outAmount ?? row.out_amount ?? "0", "CNY"),
    netAmountMinor: decimalToMinor(row.netAmount ?? row.net_amount ?? "0", "CNY"),
    count: Number(row.count ?? 0)
  };
}

function normalizeImportReport(data: TaobaoImportReportResponse): TaobaoImportReport {
  return {
    shopName: data.shopName ?? data.shop_name ?? "",
    totalRowsParsed: Number(data.totalRowsParsed ?? data.total_rows_parsed ?? 0),
    createdOrders: Number(data.createdOrders ?? data.created_orders ?? 0),
    statusChangedOrders: Number(data.statusChangedOrders ?? data.status_changed_orders ?? 0),
    closedReverted: Number(data.closedReverted ?? data.closed_reverted ?? 0),
    skippedNoChange: Number(data.skippedNoChange ?? data.skipped_no_change ?? 0),
    skippedUnpaidOrUnshipped: Number(data.skippedUnpaidOrUnshipped ?? data.skipped_unpaid_or_unshipped ?? 0),
    skippedUnknownPayment: Number(data.skippedUnknownPayment ?? data.skipped_unknown_payment ?? 0),
    autoReleasedAmountMinor: decimalToMinor(
      data.autoReleasedAmount ?? data.auto_released_amount ?? 0,
      "CNY"
    ),
    autoReleasedCount: Number(data.autoReleasedCount ?? data.auto_released_count ?? 0),
    totalFeeAmountMinor: decimalToMinor(
      data.totalFeeAmount ?? data.total_fee_amount ?? 0,
      "CNY"
    ),
    errors: data.errors ?? []
  };
}

function normalizeFlowReport(data: TaobaoFlowReportResponse): TaobaoFlowReport {
  return {
    amountMinor: decimalToMinor(data.amount, "CNY"),
    fromWalletId: String(data.fromWalletId ?? data.from_wallet_id ?? ""),
    fromWalletBalanceMinor: decimalToMinor(data.fromWalletBalance ?? data.from_wallet_balance ?? 0, "CNY"),
    toWalletId: String(data.toWalletId ?? data.to_wallet_id ?? ""),
    toWalletBalanceMinor: decimalToMinor(data.toWalletBalance ?? data.to_wallet_balance ?? 0, "CNY"),
    remark: data.remark
  };
}

export async function getTaobaoShops(): Promise<TaobaoShop[]> {
  try {
    const data = await fetchJson<TaobaoShopResponse[]>("/api/taobao/shops");
    return data.map(normalizeTaobaoShop);
  } catch {
    return mockTaobaoShops;
  }
}

export async function importTaobaoExcel(shopId: string, file: File): Promise<TaobaoImportReport> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`/api/taobao/shops/${shopId}/import`, {
    method: "POST",
    headers: {
      accept: "application/json"
    },
    body: form
  });

  const text = await response.text();

  if (!response.ok) {
    let message = `/api/taobao/shops/${shopId}/import returned ${response.status}`;
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

  const data = (text ? JSON.parse(text) : {}) as TaobaoImportReportResponse;
  return normalizeImportReport(data);
}

export async function withdrawTaobao(
  shopId: string,
  payload: { amount: string; remark?: string }
): Promise<TaobaoFlowReport> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(
    `/api/taobao/shops/${shopId}/withdraw`,
    body
  )) as TaobaoFlowReportResponse;
  return normalizeFlowReport(data);
}

export async function transferTaobaoToStoreAlipay(
  shopId: string,
  payload: { amount?: string; remark?: string; targetWalletId?: string }
): Promise<TaobaoFlowReport> {
  const body: Record<string, unknown> = {};
  if (payload.amount) {
    body.amount = payload.amount;
  }
  if (payload.remark) {
    body.remark = payload.remark;
  }
  if (payload.targetWalletId) {
    body.target_wallet_id = Number(payload.targetWalletId);
  }
  const data = (await postJson(
    `/api/taobao/shops/${shopId}/transfer-to-store-alipay`,
    body
  )) as TaobaoFlowReportResponse;
  return normalizeFlowReport(data);
}

export async function transferAssetWallets(
  fromWalletId: string,
  toWalletId: string,
  amount: string,
  remark?: string
): Promise<unknown> {
  const body: Record<string, unknown> = {
    from_wallet_id: Number(fromWalletId),
    to_wallet_id: Number(toWalletId),
    amount
  };
  if (remark) {
    body.remark = remark;
  }
  return postJson("/api/wallets/transfer", body);
}

export async function getTaobaoOrders(
  shopId: string,
  filters?: {
    status?: TaobaoOrderStatus;
    paymentMethod?: TaobaoOrderPaymentMethod;
    limit?: number;
    offset?: number;
  }
): Promise<TaobaoOrder[]> {
  try {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.paymentMethod) params.set("payment_method", filters.paymentMethod);
    if (filters?.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters?.offset !== undefined) params.set("offset", String(filters.offset));
    const query = params.toString();
    const path = query
      ? `/api/taobao/shops/${shopId}/orders?${query}`
      : `/api/taobao/shops/${shopId}/orders`;
    const data = await fetchJson<TaobaoOrderResponse[]>(path);
    return data.map(normalizeTaobaoOrder);
  } catch {
    return mockTaobaoOrders[shopId] ?? [];
  }
}

export async function getTaobaoWalletTransactions(
  shopId: string,
  walletId: string
): Promise<TaobaoWalletTransaction[]> {
  try {
    const data = await fetchJson<TaobaoWalletTransactionResponse[]>(
      `/api/taobao/shops/${shopId}/wallets/${walletId}/transactions`
    );
    return data.map(normalizeTaobaoWalletTransaction);
  } catch {
    return mockTaobaoWalletTransactions[walletId] ?? [];
  }
}

export async function getTaobaoWalletDailySummary(
  shopId: string,
  walletId: string,
  options?: { from?: string; to?: string }
): Promise<TaobaoWalletDailySummary[]> {
  const qs = new URLSearchParams();
  if (options?.from) qs.set("from", options.from);
  if (options?.to) qs.set("to", options.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  try {
    const data = await fetchJson<TaobaoWalletDailySummaryResponse[]>(
      `/api/taobao/shops/${shopId}/wallets/${walletId}/daily-summary${suffix}`
    );
    return data.map(normalizeTaobaoWalletDailySummary);
  } catch {
    return [];
  }
}

type TaiwanWalletResponse = {
  id: string | number;
  name: string;
  type?: string;
  currency?: string;
  balance: string | number;
  created_at?: string;
  createdAt?: string;
};

type TaiwanTransactionResponse = {
  id: string | number;
  wallet_id?: string | number;
  walletId?: string | number;
  amount: string | number;
  direction: "in" | "out";
  remark?: string | null;
  created_at?: string;
  createdAt?: string;
};

type TaiwanSummaryResponse = {
  total_balance?: string | number;
  totalBalance?: string | number;
  wallet_count?: number;
  walletCount?: number;
};

function normalizeTaiwanWallet(wallet: TaiwanWalletResponse): TaiwanWallet {
  return {
    id: String(wallet.id),
    name: wallet.name,
    balanceMinor: decimalToMinor(wallet.balance, "TWD"),
    createdAt: wallet.created_at ?? wallet.createdAt ?? ""
  };
}

function normalizeTaiwanTransaction(tx: TaiwanTransactionResponse, walletId?: string): TaiwanTransaction {
  return {
    id: String(tx.id),
    walletId: String(tx.wallet_id ?? tx.walletId ?? walletId ?? ""),
    amountMinor: decimalToMinor(tx.amount, "TWD"),
    direction: tx.direction,
    remark: tx.remark ?? null,
    createdAt: tx.created_at ?? tx.createdAt ?? ""
  };
}

export async function getTaiwanWallets(): Promise<TaiwanWallet[]> {
  try {
    const data = await fetchJson<TaiwanWalletResponse[]>("/api/taiwan/wallets");
    return data.map(normalizeTaiwanWallet);
  } catch {
    return mockTaiwanWallets;
  }
}

export async function creditTaiwanWallet(
  walletId: string,
  payload: { amount: string; remark?: string }
): Promise<TaiwanTransaction> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(`/api/taiwan/wallets/${walletId}/credit`, body)) as TaiwanTransactionResponse;
  return normalizeTaiwanTransaction(data, walletId);
}

export async function debitTaiwanWallet(
  walletId: string,
  payload: { amount: string; remark?: string }
): Promise<TaiwanTransaction> {
  const body: Record<string, unknown> = { amount: payload.amount };
  if (payload.remark) {
    body.remark = payload.remark;
  }
  const data = (await postJson(`/api/taiwan/wallets/${walletId}/debit`, body)) as TaiwanTransactionResponse;
  return normalizeTaiwanTransaction(data, walletId);
}

export async function getTaiwanTransactions(walletId: string): Promise<TaiwanTransaction[]> {
  try {
    const data = await fetchJson<TaiwanTransactionResponse[]>(`/api/taiwan/wallets/${walletId}/transactions`);
    return data.map((tx) => normalizeTaiwanTransaction(tx, walletId));
  } catch {
    return mockTaiwanTransactions[walletId] ?? [];
  }
}

export async function getTaiwanSummary(): Promise<TaiwanSummary> {
  try {
    const data = await fetchJson<TaiwanSummaryResponse>("/api/taiwan/summary");
    return {
      totalBalanceMinor: decimalToMinor(data.total_balance ?? data.totalBalance ?? 0, "TWD"),
      walletCount: Number(data.wallet_count ?? data.walletCount ?? 0)
    };
  } catch {
    return mockTaiwanSummary;
  }
}
