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
