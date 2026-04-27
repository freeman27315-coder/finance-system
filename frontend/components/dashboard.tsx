"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, RefreshCcw, Rows3, Wallet } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getDashboardData } from "@/lib/api";
import { formatMoney, sumMinor } from "@/lib/money";
import { sections } from "@/lib/navigation";
import type { Currency, DashboardData, ModuleSection, WalletBalance, WalletType } from "@/types";

const typeLabels: Record<WalletType, string> = {
  ASSET_RMB: "RMB 资产",
  ASSET_USDT: "USDT 资产",
  VENDOR: "供应商",
  XBOX: "XBOX",
  TAOBAO: "淘宝",
  TAIWAN: "台湾"
};

function walletsByType(wallets: WalletBalance[], walletTypes: WalletType[]) {
  return wallets.filter((wallet) => walletTypes.includes(wallet.type));
}

function primaryCurrency(wallets: WalletBalance[]): Currency {
  return wallets[0]?.currency ?? "CNY";
}

function totalByCurrency(wallets: WalletBalance[]) {
  return wallets.reduce<Record<string, number>>((result, wallet) => {
    result[wallet.currency] = (result[wallet.currency] ?? 0) + wallet.balanceMinor;
    return result;
  }, {});
}

function ModuleCard({ section, wallets }: { section: ModuleSection; wallets: WalletBalance[] }) {
  const scopedWallets = walletsByType(wallets, section.walletTypes);
  const totals = totalByCurrency(scopedWallets);
  const totalEntries = Object.entries(totals) as [Currency, number][];
  const currencies = [...new Set(scopedWallets.map((wallet) => wallet.currency))];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{section.title}</CardTitle>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{section.description}</p>
          </div>
          <Badge>{scopedWallets.length} WALLET</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {totalEntries.length > 0 ? (
            totalEntries.map(([currency, amount]) => (
              <div
                key={currency}
                className="flex items-baseline justify-between gap-3 rounded-xl border border-border/70 bg-muted/35 px-3 py-3"
              >
                <span className="text-xs font-semibold tracking-[0.12em] text-muted-foreground">{currency}</span>
                <span className="tabular-nums text-lg font-semibold text-foreground">
                  {formatMoney(amount, currency, { compact: true })}
                </span>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-muted/25 px-3 py-4 text-sm text-muted-foreground">
              等待 API 数据
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-border/70 pt-4 text-xs text-muted-foreground">
          <span>覆盖币种</span>
          <span className="font-medium text-foreground">{currencies.length > 0 ? currencies.join(" / ") : "-"}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function VendorSummary({ data }: { data: DashboardData }) {
  const summary = data.vendorSummary;
  const items = [
    {
      label: "应收",
      value: summary.receivableMinor,
      icon: ArrowDownLeft,
      tone: "success" as const
    },
    {
      label: "应付",
      value: -summary.payableMinor,
      icon: ArrowUpRight,
      tone: "danger" as const
    },
    {
      label: "净额",
      value: summary.netMinor,
      icon: ArrowLeftRight,
      tone: "transfer" as const
    }
  ];

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map((item) => {
        const Icon = item.icon;

        return (
          <Card key={item.label}>
            <CardContent className="flex items-center justify-between gap-4 p-5">
              <div>
                <div className="text-sm text-muted-foreground">{item.label}</div>
                <div className="mt-1 tabular-nums text-2xl font-semibold">
                  {formatMoney(item.value, summary.currency, {
                    accounting: item.value < 0,
                    signed: item.value > 0
                  })}
                </div>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function WalletTable({ wallets }: { wallets: WalletBalance[] }) {
  const sortedWallets = [...wallets].sort((a, b) => b.balanceMinor - a.balanceMinor);

  return (
    <Card>
      <CardHeader>
        <CardTitle>钱包余额</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>钱包</TableHead>
              <TableHead>模块</TableHead>
              <TableHead>币种</TableHead>
              <TableHead className="text-right">余额</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedWallets.map((wallet) => (
              <TableRow key={wallet.id}>
                <TableCell className="font-medium">{wallet.name}</TableCell>
                <TableCell>
                  <Badge>{typeLabels[wallet.type]}</Badge>
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{wallet.currency}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(wallet.balanceMinor, wallet.currency)}
                </TableCell>
              </TableRow>
            ))}
            {sortedWallets.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-10 text-center text-muted-foreground">
                  暂无钱包数据，等待后端接口或 mock 返回。
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function HeroPanel({ data, cnyTotal }: { data?: DashboardData; cnyTotal: number }) {
  const wallets = data?.wallets ?? [];
  const populatedModules = sections.filter(
    (section) => section.id !== "dashboard" && walletsByType(wallets, section.walletTypes).length > 0
  ).length;

  const items = [
    {
      label: "已接入模块",
      value: populatedModules,
      note: "业务模块"
    },
    {
      label: "钱包数量",
      value: wallets.length,
      note: "可展示账户"
    },
    {
      label: "主币种",
      value: primaryCurrency(wallets),
      note: "当前默认视图"
    }
  ];

  return (
    <Card className="overflow-hidden border-primary/10">
      <CardContent className="p-0">
        <div className="grid gap-0 xl:grid-cols-[1.3fr_0.7fr]">
          <div className="border-b border-border/70 p-6 xl:border-b-0 xl:border-r">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="success">CAPITAL OVERVIEW</Badge>
              <Badge tone="transfer">LOCAL PREVIEW</Badge>
            </div>
            <div className="mt-5">
              <div className="text-sm font-medium text-muted-foreground">CNY 资产总视图</div>
              <div className="mt-3 tabular-nums text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
                {formatMoney(cnyTotal, "CNY")}
              </div>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                当前首页聚合资产钱包、供应商往来和业务模块资金状态。接口可用时直读 FastAPI，不可用时自动回落 mock。
              </p>
            </div>
          </div>

          <div className="grid gap-0 divide-y divide-border/70">
            {items.map((item) => (
              <div key={item.label} className="flex items-center justify-between px-6 py-5">
                <div>
                  <div className="text-sm text-muted-foreground">{item.label}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{item.note}</div>
                </div>
                <div className="tabular-nums text-2xl font-semibold text-foreground">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function OperationsPanel({ data }: { data?: DashboardData }) {
  const wallets = data?.wallets ?? [];
  const currencyCount = new Set(wallets.map((wallet) => wallet.currency)).size;
  const summary = data?.vendorSummary;

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle>运行状态</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">接口来源、供应商净额和当前账户覆盖度。</p>
          </div>
          <Rows3 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-xl border border-border/70 bg-muted/35 px-4 py-3">
          <div className="text-xs font-semibold tracking-[0.12em] text-muted-foreground">DATA SOURCE</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge tone="transfer">FASTAPI</Badge>
            <Badge>MOCK FALLBACK</Badge>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-border/70 bg-card px-4 py-4">
            <div className="text-sm text-muted-foreground">供应商净额</div>
            <div className="mt-2 tabular-nums text-2xl font-semibold">
              {summary
                ? formatMoney(summary.netMinor, summary.currency, {
                    accounting: summary.netMinor < 0,
                    signed: summary.netMinor > 0
                  })
                : formatMoney(0, "CNY")}
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-card px-4 py-4">
            <div className="text-sm text-muted-foreground">币种覆盖</div>
            <div className="mt-2 tabular-nums text-2xl font-semibold">{currencyCount}</div>
          </div>
        </div>

        <div className="rounded-xl border border-dashed border-border px-4 py-4 text-sm leading-6 text-muted-foreground">
          金额显示已按最小单位整数处理。负值展示会根据场景切换为括号或带符号格式。
        </div>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardData
  });

  const dashboardData = data;
  const cnyWallets = dashboardData?.wallets.filter((wallet) => wallet.currency === "CNY") ?? [];
  const cnyTotal = sumMinor(cnyWallets.map((wallet) => wallet.balanceMinor));

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-3xl font-semibold tracking-normal">总览</h2>
          <p className="mt-2 text-sm text-muted-foreground">跨钱包、供应商和业务模块的资金状态汇总。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新
        </Button>
      </div>

      <HeroPanel data={dashboardData} cnyTotal={cnyTotal} />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">CNY 资产视图</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(cnyTotal, "CNY")}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">钱包数量</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">{dashboardData?.wallets.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">主币种</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">
              {primaryCurrency(dashboardData?.wallets ?? [])}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        {dashboardData ? <VendorSummary data={dashboardData} /> : <div />}
        <OperationsPanel data={dashboardData} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sections
          .filter((section) => section.id !== "dashboard")
          .map((section) => (
            <ModuleCard key={section.id} section={section} wallets={dashboardData?.wallets ?? []} />
          ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <WalletTable wallets={dashboardData?.wallets ?? []} />
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>口径说明</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">首页展示规则和当前视图口径。</p>
              </div>
              <Wallet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <div className="rounded-xl border border-border/70 bg-muted/35 px-4 py-4">
              首页默认按模块聚合，不做跨币种自动换汇。
            </div>
            <div className="rounded-xl border border-border/70 bg-muted/35 px-4 py-4">
              各模块页面保留独立操作入口，首页负责状态判断和快速定位。
            </div>
            <div className="rounded-xl border border-border/70 bg-muted/35 px-4 py-4">
              接口为空时仍会保留布局密度，避免页面退化成裸列表。
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
