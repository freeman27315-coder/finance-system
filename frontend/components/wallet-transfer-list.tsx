"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, RefreshCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  cancelWalletTransfer,
  getDashboardData,
  listWalletTransfers
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { WalletBalance, WalletTransfer } from "@/types";

// 与弹窗共用: 把汇率(数字字符串) trim 尾 0 显示
function formatRate(rate: string | number): string {
  const n = typeof rate === "number" ? rate : Number(rate);
  if (!Number.isFinite(n) || n <= 0) return "-";
  const fixed = n.toFixed(8);
  return fixed.replace(/\.?0+$/, "") || "0";
}

// 金额字符串保留 2 位(常见钱包币种), USDT/小数币种保留 6 位
function formatAmountStr(amount: string, currency: string): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return amount;
  const digits =
    currency === "USDT" || currency === "BTC" || currency === "ETH" ? 6 : 2;
  return n.toFixed(digits);
}

function formatDateOnly(value: string | null): string {
  if (!value) return "-";
  return value.length >= 10 ? value.slice(0, 10) : value;
}

// 拍平钱包树供下拉用
function flattenLeaves(wallets: WalletBalance[]): WalletBalance[] {
  const out: WalletBalance[] = [];
  const walk = (nodes: WalletBalance[]) => {
    for (const w of nodes) {
      if (!w.isGroup) out.push(w);
      if (w.children && w.children.length > 0) walk(w.children);
    }
  };
  walk(wallets);
  return out;
}

export type WalletTransferListProps = {
  // 传了就只看与该钱包相关的(from 或 to)
  walletId?: string;
  // 标题(默认"划转记录")
  title?: string;
};

export function WalletTransferList({ walletId, title = "划转记录" }: WalletTransferListProps) {
  const queryClient = useQueryClient();

  // 筛选状态
  const [filterWalletId, setFilterWalletId] = useState<string>(walletId ?? "");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [operator, setOperator] = useState<string>("");
  const [includeDeleted, setIncludeDeleted] = useState<boolean>(false);

  // 钱包下拉数据
  const { data: dashboard } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardData
  });
  const walletOptions = useMemo(
    () => flattenLeaves(dashboard?.wallets ?? []),
    [dashboard?.wallets]
  );

  // 拉划转列表 - 如果绑定 walletId, 拉 from+to 两次合并; 否则按筛选
  const effectiveWalletId = walletId ?? filterWalletId;
  const queryKey = useMemo(
    () => [
      "wallet-transfers",
      {
        walletId: effectiveWalletId,
        fromDate,
        toDate,
        operator,
        includeDeleted
      }
    ],
    [effectiveWalletId, fromDate, toDate, operator, includeDeleted]
  );

  const { data: transfers = [], isFetching, refetch } = useQuery({
    queryKey,
    queryFn: async () => {
      if (effectiveWalletId) {
        // 既看出账也看入账, 合并去重
        const [outList, inList] = await Promise.all([
          listWalletTransfers({
            fromWalletId: effectiveWalletId,
            fromDate: fromDate || undefined,
            toDate: toDate || undefined,
            operatorName: operator || undefined,
            includeDeleted
          }),
          listWalletTransfers({
            toWalletId: effectiveWalletId,
            fromDate: fromDate || undefined,
            toDate: toDate || undefined,
            operatorName: operator || undefined,
            includeDeleted
          })
        ]);
        const map = new Map<string, WalletTransfer>();
        for (const t of [...outList, ...inList]) {
          map.set(t.id, t);
        }
        return [...map.values()].sort((a, b) =>
          (a.createdAt < b.createdAt ? 1 : -1)
        );
      }
      return listWalletTransfers({
        fromDate: fromDate || undefined,
        toDate: toDate || undefined,
        operatorName: operator || undefined,
        includeDeleted
      });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: (transferId: string) => cancelWalletTransfer(transferId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["wallet-transfers"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] }),
        queryClient.invalidateQueries({ queryKey: ["asset-transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-transactions"] })
      ]);
    },
    onError: (err) => {
      window.alert(err instanceof Error ? err.message : "撤销失败");
    }
  });

  const handleCancel = (t: WalletTransfer) => {
    const desc = `从 ${t.fromWalletName ?? t.fromWalletId} 划 ${formatAmountStr(t.fromAmount, t.fromCurrency)} ${t.fromCurrency} 到 ${t.toWalletName ?? t.toWalletId}`;
    if (!confirm(`确定撤销这笔划转?\n\n${desc}\n\n撤销会反向冲销两条流水, 入账钱包余额需够扣回。`)) {
      return;
    }
    cancelMutation.mutate(t.id);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{title}</CardTitle>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} aria-hidden="true" />
            <span className="ml-1.5">刷新</span>
          </Button>
        </div>

        {/* 筛选 */}
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-5">
          {!walletId ? (
            <div className="space-y-1">
              <div className="text-[10px] font-medium text-muted-foreground">钱包</div>
              <select
                className="h-9 w-full rounded-md border border-border bg-card px-2 text-xs outline-none focus:ring-2 focus:ring-primary"
                value={filterWalletId}
                onChange={(e) => setFilterWalletId(e.target.value)}
              >
                <option value="">全部</option>
                {walletOptions.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}({w.currency})
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="space-y-1">
            <div className="text-[10px] font-medium text-muted-foreground">起始日期</div>
            <input
              type="date"
              className="h-9 w-full rounded-md border border-border bg-card px-2 text-xs outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <div className="text-[10px] font-medium text-muted-foreground">结束日期</div>
            <input
              type="date"
              className="h-9 w-full rounded-md border border-border bg-card px-2 text-xs outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <div className="text-[10px] font-medium text-muted-foreground">操作人</div>
            <input
              className="h-9 w-full rounded-md border border-border bg-card px-2 text-xs outline-none focus:ring-2 focus:ring-primary"
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              placeholder="比如 黄呈煜"
            />
          </div>
          <div className="space-y-1">
            <div className="text-[10px] font-medium text-muted-foreground">含已撤销</div>
            <label className="flex h-9 items-center gap-2 rounded-md border border-border bg-card px-2 text-xs">
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(e) => setIncludeDeleted(e.target.checked)}
              />
              <span>显示已撤销</span>
            </label>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>日期</TableHead>
              <TableHead>出账</TableHead>
              <TableHead>入账</TableHead>
              <TableHead className="text-right">汇率</TableHead>
              <TableHead>操作人</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transfers.map((t) => {
              const cancelled = Boolean(t.deletedAt);
              return (
                <TableRow
                  key={t.id}
                  className={cn(cancelled && "text-muted-foreground line-through opacity-60")}
                >
                  <TableCell className="tabular-nums text-xs">
                    {formatDateOnly(t.businessDate ?? t.createdAt)}
                    {cancelled ? (
                      <Badge tone="danger" className="ml-2">
                        已撤销
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-xs">
                    <div className="font-medium">{t.fromWalletName ?? t.fromWalletId}</div>
                    <div className="tabular-nums text-red-600 font-semibold no-underline">
                      -{formatAmountStr(t.fromAmount, t.fromCurrency)} {t.fromCurrency}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    <div className="font-medium">{t.toWalletName ?? t.toWalletId}</div>
                    <div className="tabular-nums text-green-600 font-semibold no-underline">
                      +{formatAmountStr(t.toAmount, t.toCurrency)} {t.toCurrency}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-xs">
                    <div className="flex items-center justify-end gap-1">
                      <span>1 {t.fromCurrency}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                      <span>
                        {formatRate(t.rate)} {t.toCurrency}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{t.operatorName ?? "-"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{t.note ?? "-"}</TableCell>
                  <TableCell className="text-right">
                    {cancelled ? (
                      <span className="text-[10px] text-muted-foreground">
                        {formatDateOnly(t.deletedAt)}
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-red-600 border-red-300 hover:bg-red-50"
                        onClick={() => handleCancel(t)}
                        disabled={cancelMutation.isPending}
                      >
                        <Trash2 className="h-3 w-3" aria-hidden="true" />
                        <span className="ml-1">撤销</span>
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {transfers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  {isFetching ? "加载中..." : "暂无划转记录"}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
