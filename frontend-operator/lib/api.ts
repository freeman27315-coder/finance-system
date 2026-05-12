// API 客户端 (连后端 /operator/* + /xbox/*)
// 通过 next.config.js 的 rewrites 把 /api/* 代理到 localhost:8000

import type {
  AvailableAccount,
  LoginResponse,
  OperatorClaim,
  XboxAccountDetail
} from "@/types";
import { clearSession, getToken } from "./auth";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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

  const res = await fetch(path, { ...init, headers });
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

export function claimAccount(
  accountId: number,
  operatorId: number
): Promise<OperatorClaim> {
  return request<OperatorClaim>("/api/operator/claims", {
    method: "POST",
    body: JSON.stringify({ accountId, operatorId })
  });
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

// ---------- XBOX 账号详情 (PR C 用,先暴露 stub) ----------

export async function getAccountDetail(
  accountId: number
): Promise<XboxAccountDetail | null> {
  // /xbox/accounts 返回完整列表; 后续会做单 GET /xbox/accounts/{id}
  const list = await request<XboxAccountDetail[]>("/api/xbox/accounts");
  return list.find((a) => a.id === accountId) ?? null;
}

export { ApiError };
