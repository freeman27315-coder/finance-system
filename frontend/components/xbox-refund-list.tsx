"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  cancelXboxRefund,
  getXboxWalletPoolOptions,
  listXboxRefunds
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { XboxRefund } from "@/types";

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

export function XboxRefundList() {
  const queryClient = useQueryClient();
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [actualWalletId, setActualWalletId] = useState<string>("");
  const [operator, setOperator] = useState<string>("");

  const { data: poolGroups = [] } = useQuery({
    queryKey: ["xbox-pool-options-all-no-groups"],
    queryFn: () => getXboxWalletPoolOptions({ xboxOnly: false, includeGroups: false })
  });
  const walletOptions = useMemo(
    () => poolGroups.filter((g) => g.groupCode !== "XBOX_SALES_LEDGER"),
    [poolGroups]
  );

  const queryKey = useMemo(
    () => ["xbox-refunds", { fromDate, toDate, actualWalletId, operator }],
    [fromDate, toDate, actualWalletId, operator]
  );

  const { data: refunds = [], isFetching, refetch } = useQuery({
    queryKey,
    queryFn: () =>
      listXboxRefunds({
        fromDate: fromDate || undefined,
        toDate: toDate || undefined,
        actualWalletId: actualWalletId || undefined,
        operatorName: operator || undefined
      })
  });

  const cancelMutation = useMutation({
    mutationFn: (refundId: string) => cancelXboxRefund(refundId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["xbox-refunds"] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-sale-records"] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-reconcile-report"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] })
      ]);
    },
    onError: (err) => {
      window.alert(err instanceof Error ? err.message : "撤销失败");
    }
  });

  const handleCancel = (r: XboxRefund) => {
    const desc = r.saleRecord
      ? `销售记录 #${r.saleRecord.id} ${r.saleRecord.productName}`
      : `退款 #${r.id}`;
    if (
      !confirm(
        `确定撤销这笔退款?\n\n${desc}\n金额 ${formatAmountStr(r.refundAmount, r.refundCurrency)} ${r.refundCurrency}\n\n撤销会反向冲销两条流水, 销售记录回到「未退款」。`
      )
    ) {
      return;
    }
    cancelMutation.mutate(r.id);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">退款记录</CardTitle>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} aria-hidden="true" />
            <span className="ml-1.5">刷新</span>
          </Button>
        </div>

        {/* 筛选 */}
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-4">
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
            <div className="text-[10px] font-medium text-muted-foreground">实际退款钱包</div>
            <select
              className="h-9 w-full rounded-md border border-border bg-card px-2 text-xs outline-none focus:ring-2 focus:ring-primary"
              value={actualWalletId}
              onChange={(e) => setActualWalletId(e.target.value)}
            >
              <option value="">全部</option>
              {walletOptions.map((g) => (
                <optgroup key={g.groupCode} label={`── ${g.groupLabel} ──`}>
                  {g.wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}({w.currency})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
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
        </div>
      </CardHeader>

      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>日期</TableHead>
              <TableHead>原销售记录</TableHead>
              <TableHead className="text-right">原售价</TableHead>
              <TableHead>实际退款钱包</TableHead>
              <TableHead>操作人</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {refunds.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="tabular-nums text-xs">
                  {formatDateOnly(r.businessDate ?? r.createdAt)}
                </TableCell>
                <TableCell className="text-xs">
                  {r.saleRecord ? (
                    <>
                      <div className="text-muted-foreground">
                        #{r.saleRecord.id}{" "}
                        {r.saleRecord.accountNo ?? r.saleRecord.accountName ?? ""}
                      </div>
                      <div className="font-medium truncate max-w-[220px]">
                        {r.saleRecord.productName}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        客服 {r.saleRecord.operatorName || "-"} · {r.saleRecord.walletItemLabel}
                      </div>
                    </>
                  ) : (
                    <span className="text-muted-foreground">
                      销售 #{r.originalSaleRecordId}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums text-xs font-semibold text-red-600">
                  -{formatAmountStr(r.refundAmount, r.refundCurrency)} {r.refundCurrency}
                </TableCell>
                <TableCell className="text-xs">
                  <div className="font-medium">{r.actualWalletName ?? r.actualWalletId}</div>
                  {r.theoreticalWalletName ? (
                    <div className="text-[10px] text-muted-foreground">
                      理论 {r.theoreticalWalletName}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell className="text-xs">{r.operatorName ?? "-"}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.note ?? "-"}</TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-red-600 border-red-300 hover:bg-red-50"
                    onClick={() => handleCancel(r)}
                    disabled={cancelMutation.isPending}
                  >
                    <Trash2 className="h-3 w-3" aria-hidden="true" />
                    <span className="ml-1">撤销</span>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {refunds.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  {isFetching ? "加载中..." : "暂无退款记录"}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
