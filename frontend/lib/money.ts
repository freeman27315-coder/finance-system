import type { Currency } from "@/types";

const currencyDigits: Record<Currency, number> = {
  CNY: 2,
  USDT: 6,
  USD: 2,
  GBP: 2,
  TWD: 2
};

const currencyLocales: Record<Currency, string> = {
  CNY: "zh-CN",
  USDT: "en-US",
  USD: "en-US",
  GBP: "en-GB",
  TWD: "zh-TW"
};

export function minorUnit(currency: Currency) {
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

export function minorToDisplayNumber(amountMinor: number, currency: Currency) {
  return amountMinor / 10 ** minorUnit(currency);
}

export function formatMoney(
  amountMinor: number,
  currency: Currency,
  options: { compact?: boolean; signed?: boolean; accounting?: boolean } = {}
) {
  const value = minorToDisplayNumber(amountMinor, currency);
  const digits = options.compact ? 1 : Math.min(minorUnit(currency), currency === "USDT" ? 4 : 2);
  const formatter = new Intl.NumberFormat(currencyLocales[currency] ?? "zh-CN", {
    style: currency === "USDT" ? "decimal" : "currency",
    currency: currency === "USDT" ? undefined : currency,
    notation: options.compact ? "compact" : "standard",
    minimumFractionDigits: options.compact ? 0 : Math.min(digits, 2),
    maximumFractionDigits: digits
  });
  const formatted = currency === "USDT" ? `${formatter.format(value)} USDT` : formatter.format(value);

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
