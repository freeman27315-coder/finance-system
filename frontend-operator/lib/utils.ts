import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTimeSeconds(value: string | null | undefined) {
  if (!value) return "-";
  return value.length >= 19 ? value.slice(0, 19).replace("T", " ") : value;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

/**
 * 把 Decimal 字符串的尾部多余 0 去掉, 保留客服真正填的精度。
 * 例: "23.300000" → "23.3"; "0.990000" → "0.99"; "100.000000" → "100"
 * 非数字 / null / 没有小数点 / 已经无尾零 → 原样返回
 * CEO 2026-05-14: 后端 Decimal(18,6) 序列化总是给 6 位小数, 客服不想看见。
 */
export function stripTrailingZeros(value: string | null | undefined): string {
  if (!value) return "";
  // 必须是合法数字才处理(允许负号 + 小数点)
  if (!/^-?\d+(\.\d+)?$/.test(value)) return value;
  if (!value.includes(".")) return value;
  // 去尾 0 + 可能多余的小数点
  return value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}
