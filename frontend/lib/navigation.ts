import type { ModuleSection } from "@/types";

export const sections: ModuleSection[] = [
  {
    id: "dashboard",
    title: "总览",
    href: "/",
    description: "跨钱包资金、应收应付和模块状态。",
    walletTypes: ["ASSET_RMB", "ASSET_USDT", "VENDOR", "XBOX", "TAOBAO", "TAIWAN"]
  },
  {
    id: "assets",
    title: "资产钱包",
    href: "/assets",
    description: "RMB 和 USDT 主钱包、子钱包余额。",
    walletTypes: ["ASSET_RMB", "ASSET_USDT"]
  },
  {
    id: "vendors",
    title: "供应商往来",
    href: "/vendors",
    description: "供应商应付、应收和净额。",
    walletTypes: ["VENDOR"]
  },
  {
    id: "xbox",
    title: "XBOX",
    href: "/xbox",
    description: "美国 USD 与英国 GBP 账户资金。",
    walletTypes: ["XBOX"]
  },
  {
    id: "taobao",
    title: "淘宝",
    href: "/taobao",
    description: "未结算与已结算 CNY 资金。",
    walletTypes: ["TAOBAO"]
  },
  {
    id: "taiwan",
    title: "台湾",
    href: "/taiwan",
    description: "8591余额、银行卡、超商代收金流余额。",
    walletTypes: ["TAIWAN"]
  },
  {
    id: "operators",
    title: "客服管理",
    href: "/operators",
    description: "客服账号 / TOTP 二步绑定 / 账号领取状态。",
    walletTypes: []
  }
];

export const sectionIds = sections.map((section) => section.id);

export const sectionById = Object.fromEntries(sections.map((section) => [section.id, section])) as Record<
  string,
  ModuleSection
>;
