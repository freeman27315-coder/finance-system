"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getDashboardData } from "@/lib/api";
import { formatMoney, sumMinor } from "@/lib/money";
import type { Currency, ModuleSection } from "@/types";

export function ModuleOverview({ section }: { section: ModuleSection }) {
  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardData
  });
  const topWallets = (data?.wallets ?? []).filter((wallet) => section.walletTypes.includes(wallet.type));

  // CEO 2026-05-17: 展平钱包树 (父在前, 子紧跟; 子带 parentId 用于缩进显示)
  const flatWallets = (() => {
    const out: typeof topWallets = [];
    for (const w of topWallets) {
      out.push(w);
      if (w.children) {
        for (const c of w.children) {
          out.push(c);
        }
      }
    }
    return out;
  })();

  // group 父钱包的"显示余额" = 子钱包余额之和(自动加总,不读 DB 里的 0)
  const groupBalanceMap = new Map<string, number>();
  for (const w of topWallets) {
    if (w.isGroup && w.children && w.children.length > 0) {
      groupBalanceMap.set(
        w.id,
        w.children.reduce((sum, c) => sum + c.balanceMinor, 0)
      );
    }
  }

  // 货币合计: 只数叶子钱包(避免重复计算 group)
  const totals = flatWallets.reduce<Record<string, number>>((result, wallet) => {
    if (wallet.isGroup) return result;
    result[wallet.currency] = (result[wallet.currency] ?? 0) + wallet.balanceMinor;
    return result;
  }, {});
  const totalEntries = Object.entries(totals) as [Currency, number][];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">{section.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{section.description}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {totalEntries.map(([currency, amount]) => (
          <Card key={currency}>
            <CardContent className="p-5">
              <div className="text-sm text-muted-foreground">{currency} 合计</div>
              <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(amount, currency)}</div>
            </CardContent>
          </Card>
        ))}
        {totalEntries.length === 0 ? (
          <Card>
            <CardContent className="p-5">
              <div className="text-sm text-muted-foreground">模块钱包</div>
              <div className="mt-2 tabular-nums text-3xl font-semibold">0</div>
            </CardContent>
          </Card>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>模块明细</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>钱包</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>币种</TableHead>
                <TableHead className="text-right">余额</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {flatWallets.map((wallet) => {
                const isChild = wallet.parentId != null;
                const displayBalance =
                  wallet.isGroup
                    ? groupBalanceMap.get(wallet.id) ?? 0
                    : wallet.balanceMinor;
                return (
                  <TableRow
                    key={wallet.id}
                    className={wallet.isGroup ? "bg-muted/30" : undefined}
                  >
                    <TableCell
                      className={wallet.isGroup ? "font-bold" : "font-medium"}
                      title={wallet.remark ?? undefined}
                    >
                      <span style={{ paddingLeft: isChild ? 24 : 0 }}>
                        {wallet.isGroup ? "📁 " : "└ "}
                        {wallet.name}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge>{wallet.type}</Badge>
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">{wallet.currency}</TableCell>
                    <TableCell className="text-right tabular-nums font-semibold">
                      {formatMoney(displayBalance, wallet.currency)}
                    </TableCell>
                  </TableRow>
                );
              })}
              {flatWallets.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                    当前模块暂无钱包数据
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">整数最小单位校验</div>
          <div className="mt-2 tabular-nums text-lg font-semibold">
            {sumMinor(flatWallets.filter((w) => !w.isGroup).map((wallet) => wallet.balanceMinor)).toLocaleString("zh-CN")}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
