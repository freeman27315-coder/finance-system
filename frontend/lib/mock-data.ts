import type {
  AssetTransaction,
  DashboardData,
  Vendor,
  VendorBill,
  WalletBalance,
  XboxAccount,
  XboxSummary,
  XboxTransaction
} from "@/types";

export const mockWallets: WalletBalance[] = [
  {
    id: "asset-cny-main",
    name: "RMB 主钱包",
    type: "ASSET_RMB",
    currency: "CNY",
    balanceMinor: 628_450_00
  },
  {
    id: "asset-usdt-main",
    name: "USDT 主钱包",
    type: "ASSET_USDT",
    currency: "USDT",
    balanceMinor: 184_250_000000
  },
  {
    id: "vendor-cny-net",
    name: "供应商净额",
    type: "VENDOR",
    currency: "CNY",
    balanceMinor: 76_320_00
  },
  {
    id: "xbox-us",
    name: "XBOX 美国账户",
    type: "XBOX",
    currency: "USD",
    balanceMinor: 12_840_00
  },
  {
    id: "xbox-uk",
    name: "XBOX 英国账户",
    type: "XBOX",
    currency: "GBP",
    balanceMinor: 8_620_00
  },
  {
    id: "taobao-unsettled",
    name: "淘宝未结算",
    type: "TAOBAO",
    currency: "CNY",
    balanceMinor: 93_400_00
  },
  {
    id: "taobao-settled",
    name: "淘宝已结算",
    type: "TAOBAO",
    currency: "CNY",
    balanceMinor: 41_250_00
  },
  {
    id: "taiwan-8591",
    name: "8591余额",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 385_000_00
  },
  {
    id: "taiwan-bank",
    name: "银行卡",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 128_500_00
  },
  {
    id: "taiwan-store",
    name: "超商代收金流余额",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 62_800_00
  }
];

export const mockDashboardData: DashboardData = {
  wallets: mockWallets,
  vendorSummary: {
    payableMinor: 218_700_00,
    receivableMinor: 295_020_00,
    netMinor: 76_320_00,
    currency: "CNY"
  }
};

export const mockAssetTransactions: Record<string, AssetTransaction[]> = {
  "asset-cny-main": [
    {
      id: "asset-cny-tx-1",
      walletId: "asset-cny-main",
      walletName: "RMB 主钱包",
      amountMinor: 120_000_00,
      direction: "in",
      remark: "期初转入",
      createdAt: "2026-04-20T02:30:00.000Z",
      currency: "CNY"
    },
    {
      id: "asset-cny-tx-2",
      walletId: "asset-cny-main",
      walletName: "RMB 主钱包",
      amountMinor: 18_500_00,
      direction: "out",
      remark: "供应商付款",
      createdAt: "2026-04-24T07:15:00.000Z",
      currency: "CNY"
    }
  ],
  "asset-usdt-main": [
    {
      id: "asset-usdt-tx-1",
      walletId: "asset-usdt-main",
      walletName: "USDT 主钱包",
      amountMinor: 24_000_000000,
      direction: "in",
      remark: "链上充值",
      createdAt: "2026-04-23T11:10:00.000Z",
      currency: "USDT"
    }
  ]
};

export const mockVendors: Vendor[] = [
  {
    id: "vendor-1",
    name: "华东渠道商",
    remark: "月结供应商",
    createdAt: "2026-04-10T02:00:00.000Z"
  },
  {
    id: "vendor-2",
    name: "跨境结算服务",
    remark: "USDT 相关费用",
    createdAt: "2026-04-18T06:30:00.000Z"
  }
];

export const mockVendorBills: Record<string, VendorBill[]> = {
  "vendor-1": [
    {
      id: "bill-1",
      vendorId: "vendor-1",
      vendorName: "华东渠道商",
      direction: "payable",
      amountMinor: 128_500_00,
      status: "pending",
      dueDate: "2026-05-05",
      remark: "采购款",
      createdAt: "2026-04-21T04:00:00.000Z",
      currency: "CNY"
    },
    {
      id: "bill-2",
      vendorId: "vendor-1",
      vendorName: "华东渠道商",
      direction: "receivable",
      amountMinor: 86_300_00,
      status: "settled",
      dueDate: "2026-04-25",
      remark: "返利",
      createdAt: "2026-04-15T05:00:00.000Z",
      currency: "CNY"
    }
  ],
  "vendor-2": [
    {
      id: "bill-3",
      vendorId: "vendor-2",
      vendorName: "跨境结算服务",
      direction: "receivable",
      amountMinor: 208_720_00,
      status: "pending",
      dueDate: "2026-05-12",
      remark: "服务垫款",
      createdAt: "2026-04-24T03:00:00.000Z",
      currency: "CNY"
    }
  ]
};

export const mockXboxAccounts: XboxAccount[] = [
  {
    id: "xbox-us-1",
    name: "US Game Pass",
    country: "US",
    currency: "USD",
    rmbCostMinor: 48_600_00,
    localBalanceMinor: 7_850_00,
    remark: "美国区主账户",
    createdAt: "2026-04-12T02:00:00.000Z"
  },
  {
    id: "xbox-uk-1",
    name: "UK Store",
    country: "UK",
    currency: "GBP",
    rmbCostMinor: 39_200_00,
    localBalanceMinor: 5_430_00,
    remark: "英国区主账户",
    createdAt: "2026-04-16T02:00:00.000Z"
  }
];

export const mockXboxSummary: XboxSummary = {
  usRmbCostMinor: 48_600_00,
  usLocalBalanceMinor: 7_850_00,
  ukRmbCostMinor: 39_200_00,
  ukLocalBalanceMinor: 5_430_00
};

export const mockXboxTransactions: Record<string, XboxTransaction[]> = {
  "xbox-us-1": [
    {
      id: "xbox-tx-1",
      accountId: "xbox-us-1",
      accountName: "US Game Pass",
      rmbAmountMinor: 15_000_00,
      localAmountMinor: 2_000_00,
      type: "recharge",
      remark: "礼品卡充值",
      createdAt: "2026-04-20T04:30:00.000Z",
      currency: "USD"
    },
    {
      id: "xbox-tx-2",
      accountId: "xbox-us-1",
      accountName: "US Game Pass",
      rmbAmountMinor: 0,
      localAmountMinor: 320_00,
      type: "consume",
      remark: "订阅扣费",
      createdAt: "2026-04-24T08:30:00.000Z",
      currency: "USD"
    }
  ],
  "xbox-uk-1": [
    {
      id: "xbox-tx-3",
      accountId: "xbox-uk-1",
      accountName: "UK Store",
      rmbAmountMinor: 12_000_00,
      localAmountMinor: 1_300_00,
      type: "recharge",
      remark: "英国区充值",
      createdAt: "2026-04-22T09:00:00.000Z",
      currency: "GBP"
    }
  ]
};
