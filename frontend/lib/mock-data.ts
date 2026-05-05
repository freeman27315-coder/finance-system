import type {
  AssetTransaction,
  DashboardData,
  TaiwanSummary,
  TaiwanTransaction,
  TaiwanWallet,
  TaobaoOrder,
  TaobaoShop,
  TaobaoWalletTransaction,
  Vendor,
  VendorTransaction,
  WalletBalance,
  XboxAccount,
  XboxSummary,
  XboxTransaction
} from "@/types";

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
  wallets: mockWallets
};

export const mockVendors: Vendor[] = [
  {
    id: "vendor-aurora",
    name: "极光物流",
    remark: "USDT 通道，月结",
    walletId: "vendor-wallet-aurora",
    balanceMinor: 128_500_00,
    createdAt: "2026-03-15T08:00:00.000Z"
  },
  {
    id: "vendor-blue-river",
    name: "蓝河供应链",
    remark: null,
    walletId: "vendor-wallet-blue-river",
    balanceMinor: 0,
    createdAt: "2026-03-22T09:30:00.000Z"
  },
  {
    id: "vendor-cosmo",
    name: "Cosmo 渠道商",
    remark: "境外结算",
    walletId: "vendor-wallet-cosmo",
    balanceMinor: -50_000_00,
    createdAt: "2026-04-02T03:10:00.000Z"
  }
];

export const mockVendorTransactions: Record<string, VendorTransaction[]> = {
  "vendor-aurora": [
    {
      id: "vendor-aurora-tx-1",
      walletId: "vendor-wallet-aurora",
      amountMinor: 128_500_00,
      direction: "in",
      remark: "群指令 +1285 4月物流费",
      createdAt: "2026-04-20T02:30:00.000Z"
    },
    {
      id: "vendor-aurora-tx-2",
      walletId: "vendor-wallet-aurora",
      amountMinor: 64_300_00,
      direction: "out",
      remark: "←丙火支付宝 付款 643 CNY",
      createdAt: "2026-04-15T05:10:00.000Z"
    }
  ],
  "vendor-blue-river": [
    {
      id: "vendor-blue-river-tx-1",
      walletId: "vendor-wallet-blue-river",
      amountMinor: 25_900_00,
      direction: "in",
      remark: "群指令 +259",
      createdAt: "2026-04-25T03:20:00.000Z"
    },
    {
      id: "vendor-blue-river-tx-2",
      walletId: "vendor-wallet-blue-river",
      amountMinor: 25_900_00,
      direction: "out",
      remark: "←TOM支付宝 付款 259 CNY",
      createdAt: "2026-04-26T07:00:00.000Z"
    }
  ],
  "vendor-cosmo": [
    {
      id: "vendor-cosmo-tx-1",
      walletId: "vendor-wallet-cosmo",
      amountMinor: 50_000_00,
      direction: "out",
      remark: "←FREEMAN币安 付款 70 USDT (跨币种)",
      createdAt: "2026-04-15T10:00:00.000Z"
    }
  ]
};

export const mockXboxAccounts: XboxAccount[] = [
  {
    id: "xbox-us-1",
    name: "US-Main",
    country: "US",
    currency: "USD",
    rmbCostMinor: 28_000_00,
    localBalanceMinor: 3_840_00,
    remark: "主号",
    createdAt: "2026-03-12T08:00:00.000Z"
  },
  {
    id: "xbox-us-2",
    name: "US-Backup",
    country: "US",
    currency: "USD",
    rmbCostMinor: 12_500_00,
    localBalanceMinor: 1_720_00,
    remark: null,
    createdAt: "2026-03-30T03:20:00.000Z"
  },
  {
    id: "xbox-uk-1",
    name: "UK-Main",
    country: "UK",
    currency: "GBP",
    rmbCostMinor: 18_400_00,
    localBalanceMinor: 2_100_00,
    remark: "英区主力",
    createdAt: "2026-04-02T05:00:00.000Z"
  }
];

export const mockXboxTransactions: Record<string, XboxTransaction[]> = {
  "xbox-us-1": [
    {
      id: "xbox-us-1-tx-1",
      accountId: "xbox-us-1",
      rmbAmountMinor: 14_000_00,
      localAmountMinor: 2_000_00,
      type: "recharge",
      remark: "首充",
      createdAt: "2026-03-12T08:30:00.000Z",
      currency: "USD"
    },
    {
      id: "xbox-us-1-tx-2",
      accountId: "xbox-us-1",
      rmbAmountMinor: 0,
      localAmountMinor: 160_00,
      type: "consume",
      remark: "购买游戏",
      createdAt: "2026-04-10T11:00:00.000Z",
      currency: "USD"
    }
  ],
  "xbox-us-2": [
    {
      id: "xbox-us-2-tx-1",
      accountId: "xbox-us-2",
      rmbAmountMinor: 12_500_00,
      localAmountMinor: 1_800_00,
      type: "recharge",
      remark: null,
      createdAt: "2026-03-30T03:25:00.000Z",
      currency: "USD"
    }
  ],
  "xbox-uk-1": [
    {
      id: "xbox-uk-1-tx-1",
      accountId: "xbox-uk-1",
      rmbAmountMinor: 18_400_00,
      localAmountMinor: 2_200_00,
      type: "recharge",
      remark: "英区开号",
      createdAt: "2026-04-02T05:10:00.000Z",
      currency: "GBP"
    },
    {
      id: "xbox-uk-1-tx-2",
      accountId: "xbox-uk-1",
      rmbAmountMinor: 0,
      localAmountMinor: 100_00,
      type: "consume",
      remark: "Game Pass",
      createdAt: "2026-04-20T09:00:00.000Z",
      currency: "GBP"
    }
  ]
};

export const mockXboxSummary: XboxSummary = {
  us: {
    rmbCostMinor: 40_500_00,
    localBalanceMinor: 5_560_00,
    accountCount: 2,
    currency: "USD"
  },
  uk: {
    rmbCostMinor: 18_400_00,
    localBalanceMinor: 2_100_00,
    accountCount: 1,
    currency: "GBP"
  }
};

// ---------------------------------------------------------------------------
// Taobao mock（API 失败时回退）—— 3 店铺 × 5 钱包 + 兔仔无 paymentWallet
// ---------------------------------------------------------------------------

export const mockTaobaoShops: TaobaoShop[] = [
  {
    id: "1",
    name: "丙火电玩",
    paymentWallet: { id: "3", name: "丙火网络支付宝", balanceMinor: 0 },
    unconfirmedAlipay: { id: "12", name: "丙火电玩 支付宝在途", balanceMinor: 18_400_00 },
    unconfirmedWechat: { id: "13", name: "丙火电玩 微信在途", balanceMinor: 6_280_00 },
    aggregatorFrozen: { id: "14", name: "丙火电玩 聚合支付·冻结中", balanceMinor: 42_500_00 },
    aggregatorAvailable: { id: "15", name: "丙火电玩 聚合支付·可提现", balanceMinor: 12_350_00 },
    bankCard: { id: "16", name: "丙火电玩 银行卡", balanceMinor: 80_000_00 },
    remark: null,
    createdAt: "2026-05-05T11:17:14"
  },
  {
    id: "2",
    name: "兔仔电玩",
    paymentWallet: null,
    unconfirmedAlipay: { id: "17", name: "兔仔电玩 支付宝在途", balanceMinor: 5_200_00 },
    unconfirmedWechat: { id: "18", name: "兔仔电玩 微信在途", balanceMinor: 1_800_00 },
    aggregatorFrozen: { id: "19", name: "兔仔电玩 聚合支付·冻结中", balanceMinor: 22_000_00 },
    aggregatorAvailable: { id: "20", name: "兔仔电玩 聚合支付·可提现", balanceMinor: 4_500_00 },
    bankCard: { id: "21", name: "兔仔电玩 银行卡", balanceMinor: 30_000_00 },
    remark: null,
    createdAt: "2026-05-05T11:17:14"
  },
  {
    id: "3",
    name: "小小电玩",
    paymentWallet: { id: "11", name: "小小电玩支付宝", balanceMinor: 0 },
    unconfirmedAlipay: { id: "22", name: "小小电玩 支付宝在途", balanceMinor: 9_300_00 },
    unconfirmedWechat: { id: "23", name: "小小电玩 微信在途", balanceMinor: 3_500_00 },
    aggregatorFrozen: { id: "24", name: "小小电玩 聚合支付·冻结中", balanceMinor: 28_000_00 },
    aggregatorAvailable: { id: "25", name: "小小电玩 聚合支付·可提现", balanceMinor: 7_200_00 },
    bankCard: { id: "26", name: "小小电玩 银行卡", balanceMinor: 50_000_00 },
    remark: null,
    createdAt: "2026-05-05T11:17:14"
  }
];

export const mockTaobaoOrders: Record<string, TaobaoOrder[]> = {
  "1": [
    {
      id: "1001",
      orderNumber: "TB202605040001",
      paymentMethod: "alipay",
      amountMinor: 1_280_00,
      status: "shipped_unconfirmed",
      bookkeepingWalletId: "12",
      bookkeepingTxId: "tx-1001",
      shippedAt: "2026-05-04T03:20:00.000Z",
      receivedAt: null,
      lastSyncedAt: "2026-05-05T08:00:00.000Z",
      recordedAt: "2026-05-04T05:00:00.000Z"
    },
    {
      id: "1002",
      orderNumber: "TB202605030099",
      paymentMethod: "wechat",
      amountMinor: 680_00,
      status: "received",
      bookkeepingWalletId: "14",
      bookkeepingTxId: "tx-1002",
      shippedAt: "2026-05-03T03:20:00.000Z",
      receivedAt: "2026-05-04T11:00:00.000Z",
      lastSyncedAt: "2026-05-05T08:00:00.000Z",
      recordedAt: "2026-05-03T05:00:00.000Z"
    }
  ]
};

export const mockTaobaoWalletTransactions: Record<string, TaobaoWalletTransaction[]> = {
  "14": [
    {
      id: "tx-1002",
      walletId: "14",
      amountMinor: 680_00,
      direction: "in",
      remark: "TB202605030099 已签收·冻结",
      createdAt: "2026-05-04T11:00:00.000Z",
      matureAt: "2026-05-11T11:00:00.000Z"
    }
  ],
  "12": [
    {
      id: "tx-1001",
      walletId: "12",
      amountMinor: 1_280_00,
      direction: "in",
      remark: "TB202605040001 已发货未确认",
      createdAt: "2026-05-04T05:00:00.000Z",
      matureAt: null
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

export const mockTaiwanWallets: TaiwanWallet[] = [
  {
    id: "taiwan-8591",
    name: "8591余额",
    balanceMinor: 385_000_00,
    createdAt: "2026-03-01T08:00:00.000Z"
  },
  {
    id: "taiwan-bank",
    name: "银行卡",
    balanceMinor: 128_500_00,
    createdAt: "2026-03-01T08:00:00.000Z"
  },
  {
    id: "taiwan-store",
    name: "超商代收金流余额",
    balanceMinor: 62_800_00,
    createdAt: "2026-03-01T08:00:00.000Z"
  }
];

export const mockTaiwanTransactions: Record<string, TaiwanTransaction[]> = {
  "taiwan-8591": [
    {
      id: "taiwan-8591-tx-1",
      walletId: "taiwan-8591",
      amountMinor: 200_000_00,
      direction: "in",
      remark: "期初入账",
      createdAt: "2026-03-05T03:00:00.000Z"
    },
    {
      id: "taiwan-8591-tx-2",
      walletId: "taiwan-8591",
      amountMinor: 15_000_00,
      direction: "out",
      remark: "提现",
      createdAt: "2026-04-15T07:30:00.000Z"
    }
  ],
  "taiwan-bank": [
    {
      id: "taiwan-bank-tx-1",
      walletId: "taiwan-bank",
      amountMinor: 128_500_00,
      direction: "in",
      remark: "银行汇入",
      createdAt: "2026-03-10T09:00:00.000Z"
    }
  ],
  "taiwan-store": [
    {
      id: "taiwan-store-tx-1",
      walletId: "taiwan-store",
      amountMinor: 80_000_00,
      direction: "in",
      remark: "超商代收",
      createdAt: "2026-03-20T05:00:00.000Z"
    },
    {
      id: "taiwan-store-tx-2",
      walletId: "taiwan-store",
      amountMinor: 17_200_00,
      direction: "out",
      remark: "结算转出",
      createdAt: "2026-04-12T08:00:00.000Z"
    }
  ]
};

export const mockTaiwanSummary: TaiwanSummary = {
  totalBalanceMinor: 385_000_00 + 128_500_00 + 62_800_00,
  walletCount: 3
};

