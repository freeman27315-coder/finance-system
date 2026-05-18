import type { Currency } from "@/types";

// CEO 2026-05-17: 扩展货币元数据表 - 已知货币用预设, 未知走 ISO 默认 (2 位小数 + en-US)
const currencyDigits: Record<string, number> = {
  CNY: 2, USDT: 6, USD: 2, GBP: 2, TWD: 2,
  EUR: 2, JPY: 0, KRW: 0, HKD: 2, SGD: 2, CAD: 2, AUD: 2,
  BRL: 2, MXN: 2, MYR: 2, THB: 2, PHP: 2, INR: 2, IDR: 0, VND: 0,
  RUB: 2, TRY: 2, ZAR: 2, CHF: 2, SEK: 2, NOK: 2, DKK: 2, PLN: 2,
  NZD: 2, AED: 2, SAR: 2, CLP: 0, ARS: 2, COP: 0, ILS: 2,
  CZK: 2, HUF: 2
};

const currencyLocales: Record<string, string> = {
  CNY: "zh-CN", USDT: "en-US", USD: "en-US", GBP: "en-GB", TWD: "zh-TW",
  EUR: "de-DE", JPY: "ja-JP", KRW: "ko-KR", HKD: "zh-HK", SGD: "en-SG",
  CAD: "en-CA", AUD: "en-AU", BRL: "pt-BR", MXN: "es-MX",
  INR: "en-IN", RUB: "ru-RU", TRY: "tr-TR", ZAR: "en-ZA",
  CZK: "cs-CZ", HUF: "hu-HU", PLN: "pl-PL",
  NOK: "nb-NO", SEK: "sv-SE", DKK: "da-DK", CHF: "de-CH"
};

export function minorUnit(currency: Currency): number {
  return currencyDigits[currency] ?? 2;
}

export function decimalToMinor(value: string | number, currency: Currency): number {
  const raw = String(value).trim();
  const digits = minorUnit(currency);
  const sign = raw.startsWith("-") ? -1 : 1;
  const unsigned = raw.replace(/^[+-]/, "");
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const normalizedFraction = fraction.padEnd(digits, "0").slice(0, digits);
  const units = Number.parseInt(whole || "0", 10) * 10 ** digits;
  const decimals = Number.parseInt(normalizedFraction || "0", 10);
  return sign * (units + decimals);
}

export function minorToDisplayNumber(amountMinor: number, currency: Currency): number {
  return amountMinor / 10 ** minorUnit(currency);
}

// Intl 内置支持 ISO 4217 几乎所有货币代码, 不在白名单的也能格式化, 失败兜底直接拼数字
export function formatMoney(
  amountMinor: number,
  currency: Currency,
  options: { compact?: boolean; signed?: boolean; accounting?: boolean } = {}
): string {
  const value = minorToDisplayNumber(amountMinor, currency);
  const digits = options.compact ? 1 : Math.min(minorUnit(currency), currency === "USDT" ? 4 : 2);
  const locale = currencyLocales[currency] ?? "en-US";
  let formatted: string;
  try {
    const formatter = new Intl.NumberFormat(locale, {
      style: currency === "USDT" ? "decimal" : "currency",
      currency: currency === "USDT" ? undefined : currency,
      notation: options.compact ? "compact" : "standard",
      minimumFractionDigits: options.compact ? 0 : Math.min(digits, 2),
      maximumFractionDigits: digits
    });
    formatted = currency === "USDT" ? `${formatter.format(value)} USDT` : formatter.format(value);
  } catch {
    // Intl 不认识的代码 → 用简单 number + currency code 拼
    formatted = `${value.toFixed(digits)} ${currency}`;
  }

  if (options.accounting && amountMinor < 0) {
    return `(${formatted.replace("-", "")})`;
  }
  if (options.signed && amountMinor > 0) {
    return `+${formatted}`;
  }
  return formatted;
}

export function sumMinor(values: number[]) {
  return values.reduce((total, value) => total + value, 0);
}
