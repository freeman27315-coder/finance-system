"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, RefreshCcw } from "lucide-react";
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

function flattenLeafWallets(wallets: WalletBalance[]): WalletBalance[] {
  return wallets.flatMap((wallet) =>
    wallet.children && wallet.children.length > 0
      ? wallet.isGroup
        ? flattenLeafWallets(wallet.children)
        : [{ ...wallet, children: [] }, ...flattenLeafWallets(wallet.children)]
      : wallet.isGroup
        ? []
        : [{ ...wallet, children: [] }]
  );
}

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

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{section.title}</CardTitle>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{section.description}</p>
          </div>
          <Badge>{scopedWallets.length} 钱包</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {totalEntries.length > 0 ? (
            totalEntries.map(([currency, amount]) => (
              <div key={currency} className="flex items-baseline justify-between gap-3">
                <span className="text-xs font-medium text-muted-foreground">{currency}</span>
                <span className="tabular-nums text-lg font-semibold">
                  {formatMoney(amount, currency, { compact: true })}
                </span>
              </div>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">等待 API 数据</div>
          )}
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
          </TableBody>
        </Table>
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
  const leafWallets = flattenLeafWallets(dashboardData?.wallets ?? []);
  const cnyWallets = leafWallets.filter((wallet) => wallet.currency === "CNY");
  const cnyTotal = sumMinor(cnyWallets.map((wallet) => wallet.balanceMinor));

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">总览</h2>
          <p className="mt-1 text-sm text-muted-foreground">优先读取 FastAPI；接口不可用时自动使用本地 mock 数据。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">CNY 资产视图</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(cnyTotal, "CNY")}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">钱包数量</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">{leafWallets.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">主币种</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">
              {primaryCurrency(leafWallets)}
            </div>
          </CardContent>
        </Card>
      </div>

      {dashboardData ? <VendorSummary data={dashboardData} /> : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sections
          .filter((section) => section.id !== "dashboard")
          .map((section) => (
            <ModuleCard key={section.id} section={section} wallets={leafWallets} />
          ))}
      </div>

      <WalletTable wallets={leafWallets} />
    </div>
  );
}
