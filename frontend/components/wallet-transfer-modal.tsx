"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createWalletTransfer, getDashboardData } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import type { WalletBalance } from "@/types";

// 与台湾页一致: 操作人名字存 localStorage 跨刷新保留
const OP_NAME_KEY = "taiwan-operator-name";

function getStoredOperatorName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(OP_NAME_KEY) ?? "";
}

function setStoredOperatorName(name: string) {
  if (typeof window === "undefined") return;
  if (name) localStorage.setItem(OP_NAME_KEY, name);
}

// 把 dashboard 树拍平成"叶子钱包列表"(非分组, 非已删除)
function flattenLeaves(wallets: WalletBalance[]): WalletBalance[] {
  const out: WalletBalance[] = [];
  const walk = (nodes: WalletBalance[]) => {
    for (const w of nodes) {
      if (!w.isGroup && !w.deletedAt) {
        out.push(w);
      }
      if (w.children && w.children.length > 0) {
        walk(w.children);
      }
    }
  };
  walk(wallets);
  return out;
}

// 汇率显示: 8 位小数, 自动 trim 尾 0; 但保留至少 1 位整数, 比如 "1" 而不是 "1."
function formatRate(rate: string | number): string {
  const n = typeof rate === "number" ? rate : Number(rate);
  if (!Number.isFinite(n) || n <= 0) return "-";
  const fixed = n.toFixed(8);
  // 去尾 0; 如果点后全是 0, 连小数点一起去
  return fixed.replace(/\.?0+$/, "") || "0";
}

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export type WalletTransferModalProps = {
  open: boolean;
  onClose: () => void;
  defaultFromWalletId?: string;
  onSuccess?: () => void;
};

export function WalletTransferModal({
  open,
  onClose,
  defaultFromWalletId,
  onSuccess
}: WalletTransferModalProps) {
  const queryClient = useQueryClient();

  // 拉所有钱包(资产 + 台湾)
  const { data: dashboard } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardData,
    enabled: open
  });

  const leafWallets = useMemo(
    () => flattenLeaves(dashboard?.wallets ?? []),
    [dashboard?.wallets]
  );

  const [fromWalletId, setFromWalletId] = useState<string>("");
  const [toWalletId, setToWalletId] = useState<string>("");
  const [fromAmount, setFromAmount] = useState<string>("");
  const [toAmount, setToAmount] = useState<string>("");
  const [operatorName, setOperatorName] = useState<string>("");
  const [businessDate, setBusinessDate] = useState<string>(todayISO());
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // 打开时初始化表单
  useEffect(() => {
    if (!open) return;
    setFromWalletId(defaultFromWalletId ?? "");
    setToWalletId("");
    setFromAmount("");
    setToAmount("");
    setNote("");
    setError(null);
    setBusinessDate(todayISO());
    setOperatorName(getStoredOperatorName());
  }, [open, defaultFromWalletId]);

  const fromWallet = leafWallets.find((w) => w.id === fromWalletId);
  const toWallet = leafWallets.find((w) => w.id === toWalletId);

  // 实时算汇率 = to_amount / from_amount (前端只用于展示, 提交时后端会重算)
  const rateDisplay = useMemo(() => {
    const f = Number(fromAmount);
    const t = Number(toAmount);
    if (!Number.isFinite(f) || !Number.isFinite(t) || f <= 0 || t <= 0) return "-";
    return formatRate(t / f);
  }, [fromAmount, toAmount]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!fromWalletId) throw new Error("请选择出账钱包");
      if (!toWalletId) throw new Error("请选择入账钱包");
      if (fromWalletId === toWalletId) throw new Error("出账和入账不能是同一个钱包");
      const f = Number(fromAmount);
      const t = Number(toAmount);
      if (!fromAmount.trim() || !Number.isFinite(f) || f <= 0) {
        throw new Error("出账金额必须大于 0");
      }
      if (!toAmount.trim() || !Number.isFinite(t) || t <= 0) {
        throw new Error("入账金额必须大于 0");
      }
      const opName = operatorName.trim();
      if (opName) setStoredOperatorName(opName);
      return createWalletTransfer({
        fromWalletId,
        toWalletId,
        fromAmount: fromAmount.trim(),
        toAmount: toAmount.trim(),
        businessDate: businessDate || undefined,
        operatorName: opName || undefined,
        note: note.trim() || undefined
      });
    },
    onSuccess: async () => {
      // 刷各页缓存
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] }),
        queryClient.invalidateQueries({ queryKey: ["asset-transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["taiwan-transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["wallet-transfers"] })
      ]);
      onSuccess?.();
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "划转失败")
  });

  if (!open) return null;

  // 入账钱包下拉应排除当前出账钱包
  const toCandidates = leafWallets.filter((w) => w.id !== fromWalletId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">钱包划转</CardTitle>
          <div className="text-xs text-muted-foreground">
            从一个钱包搬钱到另一个(支持跨币种), 系统按"入账/出账"自动算汇率
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 出账钱包 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">出账钱包</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={fromWalletId}
              onChange={(e) => setFromWalletId(e.target.value)}
            >
              <option value="">-- 选择 --</option>
              {leafWallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}({w.currency}, 余额 {formatMoney(w.balanceMinor, w.currency)})
                </option>
              ))}
            </select>
          </div>

          {/* 出账金额 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              出账金额{fromWallet ? `(${fromWallet.currency})` : ""}
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={fromAmount}
              onChange={(e) => setFromAmount(e.target.value)}
              placeholder="例: 1000"
              type="number"
              min="0"
              step="0.000001"
              inputMode="decimal"
            />
          </div>

          {/* 入账钱包 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">入账钱包</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={toWalletId}
              onChange={(e) => setToWalletId(e.target.value)}
            >
              <option value="">-- 选择 --</option>
              {toCandidates.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}({w.currency}, 余额 {formatMoney(w.balanceMinor, w.currency)})
                </option>
              ))}
            </select>
          </div>

          {/* 入账金额 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              入账金额{toWallet ? `(${toWallet.currency})` : ""}
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={toAmount}
              onChange={(e) => setToAmount(e.target.value)}
              placeholder="例: 30"
              type="number"
              min="0"
              step="0.000001"
              inputMode="decimal"
            />
          </div>

          {/* 当前汇率(只读) */}
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
            <div className="text-muted-foreground">当前汇率(入账 / 出账)</div>
            <div className="mt-0.5 flex items-center gap-2 text-sm font-semibold tabular-nums">
              {fromWallet ? <span>1 {fromWallet.currency}</span> : <span>1 ?</span>}
              <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
              <span>
                {rateDisplay} {toWallet?.currency ?? "?"}
              </span>
            </div>
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

          {/* 备注 */}
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">备注(选填)</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="例: 台币归集"
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
              disabled={mutation.isPending || !fromWalletId || !toWalletId}
            >
              {mutation.isPending ? "提交中..." : "确认划转"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
