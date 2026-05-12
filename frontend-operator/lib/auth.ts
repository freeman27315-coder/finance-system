// 客服登录态管理: token + operator info 存 localStorage
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const TOKEN_KEY = "operator_token";
const OPERATOR_KEY = "operator_info";

export type StoredOperator = {
  id: number;
  loginName: string;
  displayName: string;
};

export function saveSession(token: string, operator: StoredOperator) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(OPERATOR_KEY, JSON.stringify(operator));
}

export function clearSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(OPERATOR_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getOperator(): StoredOperator | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(OPERATOR_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredOperator;
  } catch {
    return null;
  }
}

/**
 * 守卫 hook: 没 token 自动跳 /login
 * @returns 当前登录的 operator (loading 期间是 null)
 */
export function useRequireAuth(): {
  operator: StoredOperator | null;
  loading: boolean;
} {
  const router = useRouter();
  const [operator, setOperator] = useState<StoredOperator | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    const op = getOperator();
    if (!token || !op) {
      router.replace("/login");
      return;
    }
    setOperator(op);
    setLoading(false);
  }, [router]);

  return { operator, loading };
}

/** 反向守卫: 已登录则跳 / (登录页用) */
export function useRedirectIfLoggedIn() {
  const router = useRouter();
  useEffect(() => {
    if (getToken() && getOperator()) {
      router.replace("/");
    }
  }, [router]);
}
