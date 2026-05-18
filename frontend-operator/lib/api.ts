// API 客户端 (连后端 /operator/* + /xbox/*)
//
// CEO 2026-05-14: 改为直连后端 (绕过 Next.js dev proxy 的 30s 默认超时,
// Playwright 同步会跑 60s+)。后端开了 CORS 允许 :3100 直连。
// API_BASE 默认 http://localhost:8002, 后端换端口时改 NEXT_PUBLIC_API_BASE。
//
// 路径上原本带 /api 前缀的(经 Next.js rewrites 代理),现在直接打到 BASE。

import type {
  AvailableAccount,
  ClaimedAccount,
  LoginResponse,
  OperatorClaim,
  OperatorOrder,
  SaleCurrency,
  SyncOrdersResult,
  WalletMethod,
  XboxAccountDetail
} from "@/types";
import { clearSession, getToken } from "./auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.trim() || "http://localhost:8002";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function _resolveUrl(path: string): string {
  // 兼容历史代码: 把 /api/xxx 改写到 BASE/xxx; 已是绝对 URL 不动
  if (/^https?:\/\//i.test(path)) return path;
  const stripped = path.replace(/^\/api(\/|$)/, "/");
  return `${API_BASE}${stripped}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const token = getToken();
  if (token) {
    headers.set("authorization", `Bearer ${token}`);
  }

  const res = await fetch(_resolveUrl(path), { ...init, headers });
  const text = await res.text();

  if (!res.ok) {
    // 401 → 自动清登录态(由调用方决定是否跳转)
    if (res.status === 401) {
      clearSession();
    }
    let detail = `${path} returned ${res.status}`;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: string };
        detail = parsed.detail ?? text;
      } catch {
        detail = text;
      }
    }
    throw new ApiError(res.status, detail);
  }

  return text ? (JSON.parse(text) as T) : (null as unknown as T);
}

// ---------- Auth ----------

export function loginOperator(payload: {
  loginName: string;
  password: string;
  totpCode: string;
}): Promise<LoginResponse> {
  return request<LoginResponse>("/api/operator/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

// ---------- 账号领取 ----------

export function getAvailableAccounts(): Promise<AvailableAccount[]> {
  return request<AvailableAccount[]>("/api/operator/available-accounts");
}

export function getMyClaims(operatorId: number): Promise<OperatorClaim[]> {
  return request<OperatorClaim[]>(
    `/api/operator/operators/${operatorId}/claims`
  );
}

// CEO 2026-05-17: 拿"我的领取"全量账号信息(供"我的领取"卡片渲染)
export function getMyClaimedAccounts(operatorId: number): Promise<ClaimedAccount[]> {
  return request<ClaimedAccount[]>(
    `/api/operator/operators/${operatorId}/claimed-accounts`
  );
}

export function claimAccount(
  accountId: number,
  operatorId: number
): Promise<OperatorClaim> {
  return request<OperatorClaim>("/api/operator/claims", {
    method: "POST",
    body: JSON.stringify({ accountId, operatorId })
  });
}

// CEO 2026-05-17: 客服按需刷新单条账号余额(可领取池里 / 已领取账号都能用)
export type OperatorRefreshBalanceResult = {
  success: boolean;
  balance: string | null;
  currency: string | null;
  country: string | null;
  message: string | null;
  lastSyncedAt: string | null;
};
export function refreshAccountBalance(accountId: number): Promise<OperatorRefreshBalanceResult> {
  return request<OperatorRefreshBalanceResult>(
    `/api/operator/accounts/${accountId}/refresh-balance`,
    { method: "POST" }
  );
}

export function returnClaim(
  claimId: number,
  operatorId: number
): Promise<OperatorClaim> {
  return request<OperatorClaim>(`/api/operator/claims/${claimId}/return`, {
    method: "POST",
    body: JSON.stringify({ operatorId })
  });
}

// ---------- XBOX 账号详情 / 同步 / 补销售 (PR C) ----------

export function getAccountDetail(
  accountId: number,
  operatorId: number
): Promise<XboxAccountDetail> {
  return request<XboxAccountDetail>(
    `/api/operator/accounts/${accountId}?operatorId=${operatorId}`
  );
}

export function syncOrders(
  accountId: number,
  operatorId: number,
  count: number
): Promise<SyncOrdersResult> {
  return request<SyncOrdersResult>(
    `/api/operator/accounts/${accountId}/sync-orders`,
    {
      method: "POST",
      body: JSON.stringify({ operatorId, count })
    }
  );
}

export function getAccountOrders(
  accountId: number,
  operatorId: number,
  onlyPending = false // CEO 2026-05-12: 默认返回全部历史订单
): Promise<OperatorOrder[]> {
  return request<OperatorOrder[]>(
    `/api/operator/accounts/${accountId}/orders?operatorId=${operatorId}&onlyPending=${onlyPending}`
  );
}

export function completeOrder(
  orderId: number,
  payload: {
    operatorId: number;
    // CEO 2026-05-12 inline 编辑: 所有补销售字段都可选,只传改的
    productName?: string;
    salePrice?: string;
    saleCurrency?: SaleCurrency;
    walletMethodId?: number;
    walletItemId?: number;
    remark?: string;
  }
): Promise<OperatorOrder> {
  return request<OperatorOrder>(
    `/api/operator/orders/${orderId}/completion`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

// 钱包设置(收款方式 / 备注模板) — 复用 CEO 后台的端点
export function getWalletMethods(): Promise<WalletMethod[]> {
  return request<WalletMethod[]>("/api/xbox/wallet-settings?onlyActive=true");
}

export { ApiError };
