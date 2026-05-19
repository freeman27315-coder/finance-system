"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createXboxRefund,
  getXboxAccounts,
  getXboxWalletPoolOptions
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import type { Currency, XboxSaleRecord } from "@/types";

// 与划转弹窗一致, 操作人名字存 localStorage
const OP_NAME_KEY = "taiwan-operator-name";

function getStoredOperatorName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(OP_NAME_KEY) ?? "";
}

function setStoredOperatorName(name: string) {
  if (typeof window === "undefined") return;
  if (name) localStorage.setItem(OP_NAME_KEY, name);
}

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export type XboxRefundModalProps = {
  saleRecord: XboxSaleRecord;
  onClose: () => void;
  onSuccess?: () => void;
};

export function XboxRefundModal({ saleRecord, onClose, onSuccess }: XboxRefundModalProps) {
  const queryClient = useQueryClient();

  // 拉所有钱包(用 includeGroups=false 排除分组钱包) - 列出所有币种
  const { data: poolGroups = [] } = useQuery({
    queryKey: ["xbox-pool-options-all-no-groups"],
    queryFn: () => getXboxWalletPoolOptions({ xboxOnly: false, includeGroups: false })
  });

  // 拉账号(显示账号编号)
  const { data: accounts = [] } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const account = accounts.find((a) => a.id === saleRecord.accountId);

  const [actualWalletId, setActualWalletId] = useState<string>("");
  const [operatorName, setOperatorName] = useState<string>("");
  const [businessDate, setBusinessDate] = useState<string>(todayISO());
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  // 默认按销售币种过滤, 可关闭"显示全部"
  const [filterByCurrency, setFilterByCurrency] = useState<boolean>(true);

  useEffect(() => {
    setActualWalletId("");
    setNote("");
    setError(null);
    setBusinessDate(todayISO());
    setOperatorName(getStoredOperatorName());
  }, [saleRecord.id]);

  // 找原销售记录的理论钱包名 (从 pool 选项里找)
  const theoreticalWallet = useMemo(() => {
    for (const g of poolGroups) {
      const w = g.wallets.find((x) => x.id === saleRecord.walletPoolId);
      if (w) return w;
    }
    return null;
  }, [poolGroups, saleRecord.walletPoolId]);

  // 实际钱包候选: 排除 XBOX_SALES_LEDGER (那是理论钱包池), 按需按币种过滤
  const candidateGroups = useMemo(() => {
    const groups = poolGroups.filter((g) => g.groupCode !== "XBOX_SALES_LEDGER");
    if (!filterByCurrency) return groups;
    return groups
      .map((g) => ({
        ...g,
        wallets: g.wallets.filter((w) => w.currency === saleRecord.saleCurrency)
      }))
      .filter((g) => g.wallets.length > 0);
  }, [poolGroups, filterByCurrency, saleRecord.saleCurrency]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!actualWalletId) throw new Error("请选择实际退款钱包");
      const opName = operatorName.trim();
      if (opName) setStoredOperatorName(opName);
      return createXboxRefund({
        saleRecordId: saleRecord.id,
        actualWalletId,
        businessDate: businessDate || undefined,
        operatorName: opName || undefined,
        note: note.trim() || undefined
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["xbox-sale-records"] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-refunds"] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-reconcile-report"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] })
      ]);
      onSuccess?.();
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "退款失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">XBOX 销售记录退款</CardTitle>
          <div className="text-xs text-muted-foreground">
            全额退款。提交后销售记录标「已退款」, 实际钱包与理论钱包同时 OUT 一笔。
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 原销售记录摘要(只读) */}
          <div className="rounded-md border border-border bg-muted/30 p-3 text-xs space-y-1">
            <div className="font-semibold text-sm text-foreground">销售记录 #{saleRecord.id}</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
              <div>
                <span className="text-foreground/60">账号:</span>{" "}
                <span className="font-medium text-foreground">
                  {account?.accountNo ?? account?.name ?? "-"}
                </span>
              </div>
              <div>
                <span className="text-foreground/60">客服:</span>{" "}
                <span className="font-medium text-foreground">{saleRecord.operatorName || "-"}</span>
              </div>
              <div className="col-span-2">
                <span className="text-foreground/60">商品:</span>{" "}
                <span className="font-medium text-foreground">{saleRecord.productName}</span>
              </div>
              <div>
                <span className="text-foreground/60">原售价:</span>{" "}
                <span className="font-semibold text-emerald-600">
                  {formatMoney(saleRecord.salePrice, saleRecord.saleCurrency as Currency)}
                </span>
              </div>
              <div>
                <span className="text-foreground/60">理论钱包:</span>{" "}
                <span className="font-medium text-foreground">
                  {theoreticalWallet?.name ?? saleRecord.walletItemLabel}
                </span>
              </div>
            </div>
          </div>

          {/* 退款金额(只读) */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">退款金额(全额, 不可改)</div>
            <div className="h-10 flex items-center rounded-md border border-border bg-muted/30 px-3 text-sm font-semibold tabular-nums">
              {formatMoney(saleRecord.salePrice, saleRecord.saleCurrency as Currency)}
            </div>
          </div>

          {/* 实际退款钱包 */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium text-muted-foreground">实际退款钱包</div>
              <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <input
                  type="checkbox"
                  checked={!filterByCurrency}
                  onChange={(e) => setFilterByCurrency(!e.target.checked)}
                />
                显示所有币种钱包
              </label>
            </div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={actualWalletId}
              onChange={(e) => setActualWalletId(e.target.value)}
            >
              <option value="">-- 选择实际钱包 --</option>
              {candidateGroups.map((g) => (
                <optgroup key={g.groupCode} label={`── ${g.groupLabel} ──`}>
                  {g.wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.fullPath}({w.currency})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <div className="text-[10px] text-muted-foreground">
              {filterByCurrency
                ? `仅显示 ${saleRecord.saleCurrency} 钱包(取消勾选可看全部)`
                : "显示全部币种钱包"}
            </div>
          </div>

          {/* 业务日期 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">业务日期</div>
            <input
              type="date"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
            />
          </div>

          {/* 操作人 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">操作人</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={operatorName}
              onChange={(e) => setOperatorName(e.target.value)}
              placeholder="比如 黄呈煜 / 李睿旭"
            />
            <div className="text-[10px] text-muted-foreground">下次会自动填上次的名字</div>
          </div>

          {/* 备注 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">备注(选填)</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="例: 客户太久没等到充值, 全额退"
            />
          </div>

          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-600">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              取消
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || !actualWalletId}
            >
              {mutation.isPending ? "提交中..." : "确认退款"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
