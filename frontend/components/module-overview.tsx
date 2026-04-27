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
  const wallets = (data?.wallets ?? []).filter((wallet) => section.walletTypes.includes(wallet.type));
  const totals = wallets.reduce<Record<string, number>>((result, wallet) => {
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
              {wallets.map((wallet) => (
                <TableRow key={wallet.id}>
                  <TableCell className="font-medium">{wallet.name}</TableCell>
                  <TableCell>
                    <Badge>{wallet.type}</Badge>
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">{wallet.currency}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">
                    {formatMoney(wallet.balanceMinor, wallet.currency)}
                  </TableCell>
                </TableRow>
              ))}
              {wallets.length === 0 ? (
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
            {sumMinor(wallets.map((wallet) => wallet.balanceMinor)).toLocaleString("zh-CN")}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
