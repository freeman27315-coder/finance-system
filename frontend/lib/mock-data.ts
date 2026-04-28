import type { AssetTransaction, DashboardData, Vendor, VendorBill, WalletBalance } from "@/types";

export const mockWallets: WalletBalance[] = [
  {
    id: "asset-cny-root",
    name: "RMB钱包",
    type: "ASSET_RMB",
    currency: "CNY",
    balanceMinor: 628_450_00,
    isGroup: true,
    remark: null,
    deletedAt: null,
    children: [
      {
        id: "asset-cny-alipay",
        name: "支付宝钱包",
        type: "ASSET_RMB",
        currency: "CNY",
        balanceMinor: 508_450_00,
        isGroup: true,
        parentId: "asset-cny-root",
        remark: null,
        deletedAt: null,
        children: [
          {
            id: "asset-cny-bh",
            name: "丙火网络支付宝",
            type: "ASSET_RMB",
            currency: "CNY",
            balanceMinor: 228_150_00,
            isGroup: false,
            parentId: "asset-cny-alipay",
            remark: null,
            deletedAt: null
          },
          {
            id: "asset-cny-tom",
            name: "TOM支付宝",
            type: "ASSET_RMB",
            currency: "CNY",
            balanceMinor: 164_300_00,
            isGroup: false,
            parentId: "asset-cny-alipay",
            remark: null,
            deletedAt: null
          },
          {
            id: "asset-cny-boss",
            name: "BOSS支付宝",
            type: "ASSET_RMB",
            currency: "CNY",
            balanceMinor: 116_000_00,
            isGroup: false,
            parentId: "asset-cny-alipay",
            remark: null,
            deletedAt: null
          }
        ]
      },
      {
        id: "asset-cny-wechat",
        name: "微信钱包",
        type: "ASSET_RMB",
        currency: "CNY",
        balanceMinor: 120_000_00,
        isGroup: true,
        parentId: "asset-cny-root",
        remark: null,
        deletedAt: null,
        children: [
          {
            id: "asset-cny-dancer",
            name: "跳舞姬微信",
            type: "ASSET_RMB",
            currency: "CNY",
            balanceMinor: 120_000_00,
            isGroup: false,
            parentId: "asset-cny-wechat",
            remark: null,
            deletedAt: null
          }
        ]
      }
    ]
  },
  {
    id: "asset-usdt-root",
    name: "USDT钱包",
    type: "ASSET_USDT",
    currency: "USDT",
    balanceMinor: 184_250_000000,
    isGroup: true,
    remark: null,
    deletedAt: null,
    children: [
      {
        id: "asset-usdt-freeman",
        name: "FREEMAN币安",
        type: "ASSET_USDT",
        currency: "USDT",
        balanceMinor: 96_500_000000,
        isGroup: false,
        parentId: "asset-usdt-root",
        remark: null,
        deletedAt: null
      },
      {
        id: "asset-usdt-zhang",
        name: "张总币安",
        type: "ASSET_USDT",
        currency: "USDT",
        balanceMinor: 87_750_000000,
        isGroup: false,
        parentId: "asset-usdt-root",
        remark: null,
        deletedAt: null
      }
    ]
  },
  {
    id: "vendor-cny-net",
    name: "供应商净额",
    type: "VENDOR",
    currency: "CNY",
    balanceMinor: 76_320_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "xbox-us",
    name: "XBOX 美国账户",
    type: "XBOX",
    currency: "USD",
    balanceMinor: 12_840_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "xbox-uk",
    name: "XBOX 英国账户",
    type: "XBOX",
    currency: "GBP",
    balanceMinor: 8_620_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "taobao-unsettled",
    name: "淘宝未结算",
    type: "TAOBAO",
    currency: "CNY",
    balanceMinor: 93_400_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "taobao-settled",
    name: "淘宝已结算",
    type: "TAOBAO",
    currency: "CNY",
    balanceMinor: 41_250_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "taiwan-8591",
    name: "8591余额",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 385_000_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "taiwan-bank",
    name: "银行卡",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 128_500_00,
    isGroup: false,
    remark: null,
    deletedAt: null
  },
  {
    id: "taiwan-store",
    name: "超商代收金流余额",
    type: "TAIWAN",
    currency: "TWD",
    balanceMinor: 62_800_00,
    isGroup: false,
    remark: null,
    deletedAt: null
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

export const mockVendors: Vendor[] = [
  {
    id: "vendor-aurora",
    name: "极光物流",
    remark: "USDT 通道，月结",
    createdAt: "2026-03-15T08:00:00.000Z"
  },
  {
    id: "vendor-blue-river",
    name: "蓝河供应链",
    remark: null,
    createdAt: "2026-03-22T09:30:00.000Z"
  },
  {
    id: "vendor-cosmo",
    name: "Cosmo 渠道商",
    remark: "境外结算",
    createdAt: "2026-04-02T03:10:00.000Z"
  }
];

export const mockVendorBills: Record<string, VendorBill[]> = {
  "vendor-aurora": [
    {
      id: "bill-aurora-1",
      vendorId: "vendor-aurora",
      direction: "payable",
      amountMinor: 128_500_00,
      currency: "CNY",
      status: "pending",
      dueDate: "2026-05-10",
      remark: "4 月物流费",
      createdAt: "2026-04-20T02:30:00.000Z"
    },
    {
      id: "bill-aurora-2",
      vendorId: "vendor-aurora",
      direction: "payable",
      amountMinor: 64_300_00,
      currency: "CNY",
      status: "settled",
      dueDate: "2026-04-05",
      remark: "3 月尾款",
      createdAt: "2026-03-28T05:00:00.000Z"
    }
  ],
  "vendor-blue-river": [
    {
      id: "bill-blue-1",
      vendorId: "vendor-blue-river",
      direction: "receivable",
      amountMinor: 188_000_00,
      currency: "CNY",
      status: "pending",
      dueDate: "2026-05-15",
      remark: "渠道返点",
      createdAt: "2026-04-18T07:00:00.000Z"
    },
    {
      id: "bill-blue-2",
      vendorId: "vendor-blue-river",
      direction: "payable",
      amountMinor: 25_900_00,
      currency: "CNY",
      status: "pending",
      dueDate: null,
      remark: null,
      createdAt: "2026-04-25T03:20:00.000Z"
    }
  ],
  "vendor-cosmo": [
    {
      id: "bill-cosmo-1",
      vendorId: "vendor-cosmo",
      direction: "receivable",
      amountMinor: 107_020_00,
      currency: "CNY",
      status: "pending",
      dueDate: "2026-05-20",
      remark: "Cosmo 季度返佣",
      createdAt: "2026-04-15T10:00:00.000Z"
    },
    {
      id: "bill-cosmo-2",
      vendorId: "vendor-cosmo",
      direction: "receivable",
      amountMinor: 32_000_00,
      currency: "CNY",
      status: "settled",
      dueDate: "2026-04-10",
      remark: null,
      createdAt: "2026-03-30T06:30:00.000Z"
    }
  ]
};

export const mockAssetTransactions: Record<string, AssetTransaction[]> = {
  "asset-cny-bh": [
    {
      id: "asset-cny-bh-tx-1",
      walletId: "asset-cny-bh",
      walletName: "丙火网络支付宝",
      amountMinor: 88_000_00,
      direction: "in",
      remark: "期初转入",
      createdAt: "2026-04-20T02:30:00.000Z",
      currency: "CNY"
    },
    {
      id: "asset-cny-bh-tx-2",
      walletId: "asset-cny-bh",
      walletName: "丙火网络支付宝",
      amountMinor: 18_500_00,
      direction: "out",
      remark: "供应商付款",
      createdAt: "2026-04-24T07:15:00.000Z",
      currency: "CNY"
    }
  ],
  "asset-cny-tom": [
    {
      id: "asset-cny-tom-tx-1",
      walletId: "asset-cny-tom",
      walletName: "TOM支付宝",
      amountMinor: 64_300_00,
      direction: "in",
      remark: "渠道回款",
      createdAt: "2026-04-21T10:10:00.000Z",
      currency: "CNY"
    }
  ],
  "asset-usdt-freeman": [
    {
      id: "asset-usdt-freeman-tx-1",
      walletId: "asset-usdt-freeman",
      walletName: "FREEMAN币安",
      amountMinor: 24_000_000000,
      direction: "in",
      remark: "链上充值",
      createdAt: "2026-04-23T11:10:00.000Z",
      currency: "USDT"
    }
  ],
  "asset-usdt-zhang": [
    {
      id: "asset-usdt-zhang-tx-1",
      walletId: "asset-usdt-zhang",
      walletName: "张总币安",
      amountMinor: 12_400_000000,
      direction: "out",
      remark: "划拨",
      createdAt: "2026-04-24T11:10:00.000Z",
      currency: "USDT"
    }
  ]
};
