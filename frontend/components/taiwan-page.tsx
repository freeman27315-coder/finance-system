"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ListOrdered,
  RefreshCcw,
  Wallet as WalletIcon
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  creditTaiwanWallet,
  debitTaiwanWallet,
  getTaiwanSummary,
  getTaiwanTransactions,
  getTaiwanWallets
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { TaiwanWallet } from "@/types";

function formatDateTime(value: string) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

function SummaryCard() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["taiwan-summary"],
    queryFn: getTaiwanSummary
  });

  const total = data?.totalBalanceMinor ?? 0;
  const count = data?.walletCount ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新汇总
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Card className="border border-emerald-500/40">
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">三钱包合计余额</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold text-emerald-600">
                {formatMoney(total, "TWD")}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
              <WalletIcon className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">钱包数</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold">{count}</div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
              <WalletIcon className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CreditModal({ wallet, onClose }: { wallet: TaiwanWallet; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!amount || Number(amount) <= 0) {
        throw new Error("入账金额必须大于 0");
      }
      return creditTaiwanWallet(wallet.id, {
        amount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-transactions", wallet.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "入账失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>入账 · {wallet.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">入账金额（TWD）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="入账金额"
              type="number"
              min="0"
              step="0.01"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填）</div>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
              placeholder="备注"
            />
          </div>
          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              取消
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? "提交中..." : "确认入账"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DebitModal({ wallet, onClose }: { wallet: TaiwanWallet; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!amount || Number(amount) <= 0) {
        throw new Error("出账金额必须大于 0");
      }
      return debitTaiwanWallet(wallet.id, {
        amount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-transactions", wallet.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "出账失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>出账 · {wallet.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">出账金额（TWD）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="出账金额"
              type="number"
              min="0"
              step="0.01"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填）</div>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
              placeholder="备注"
            />
          </div>
          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              取消
            </Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? "提交中..." : "确认出账"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TransactionsModal({ wallet, onClose }: { wallet: TaiwanWallet; onClose: () => void }) {
  const { data: transactions = [], isFetching } = useQuery({
    queryKey: ["taiwan-transactions", wallet.id],
    queryFn: () => getTaiwanTransactions(wallet.id)
  });

  const sorted = [...transactions].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-3xl">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>{wallet.name} · 流水</CardTitle>
            <Button variant="ghost" size="sm" onClick={onClose}>
              关闭
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>方向</TableHead>
                <TableHead className="text-right">金额</TableHead>
                <TableHead>备注</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((tx) => {
                const isIn = tx.direction === "in";
                return (
                  <TableRow key={tx.id}>
                    <TableCell>
                      <Badge tone={isIn ? "success" : "danger"}>
                        {isIn ? "入账" : "出账"}
                      </Badge>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums font-semibold",
                        isIn ? "text-green-600" : "text-red-600"
                      )}
                    >
                      {formatMoney(tx.amountMinor, "TWD")}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{tx.remark ?? "-"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(tx.createdAt)}</TableCell>
                  </TableRow>
                );
              })}
              {sorted.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                    {isFetching ? "加载中..." : "暂无流水"}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export function TaiwanPage() {
  const [creditTarget, setCreditTarget] = useState<TaiwanWallet | null>(null);
  const [debitTarget, setDebitTarget] = useState<TaiwanWallet | null>(null);
  const [transactionsTarget, setTransactionsTarget] = useState<TaiwanWallet | null>(null);

  const { data: wallets = [], isFetching, refetch } = useQuery({
    queryKey: ["taiwan-wallets"],
    queryFn: getTaiwanWallets
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">台湾钱包</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            8591 余额 / 银行卡 / 超商代收金流余额，三个固定钱包，仅支持入出账与流水查询。
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新钱包
        </Button>
      </div>

      <SummaryCard />

      <div className="grid gap-3 md:grid-cols-3">
        {wallets.map((wallet) => (
          <Card key={wallet.id} className="border border-emerald-500/30">
            <CardHeader>
              <CardTitle className="text-base">{wallet.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="text-sm text-muted-foreground">余额</div>
                <div className="mt-1 tabular-nums text-3xl font-semibold text-emerald-600">
                  {formatMoney(wallet.balanceMinor, "TWD")}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setCreditTarget(wallet)}>
                  <ArrowDownLeft className="h-4 w-4 text-green-600" aria-hidden="true" />
                  入账
                </Button>
                <Button size="sm" variant="outline" onClick={() => setDebitTarget(wallet)}>
                  <ArrowUpRight className="h-4 w-4 text-red-600" aria-hidden="true" />
                  出账
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setTransactionsTarget(wallet)}>
                  <ListOrdered className="h-4 w-4" aria-hidden="true" />
                  流水
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {wallets.length === 0 && !isFetching ? (
          <Card className="md:col-span-3">
            <CardContent className="py-8 text-center text-muted-foreground">暂无钱包</CardContent>
          </Card>
        ) : null}
      </div>

      {creditTarget ? (
        <CreditModal wallet={creditTarget} onClose={() => setCreditTarget(null)} />
      ) : null}
      {debitTarget ? (
        <DebitModal wallet={debitTarget} onClose={() => setDebitTarget(null)} />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal wallet={transactionsTarget} onClose={() => setTransactionsTarget(null)} />
      ) : null}
    </div>
  );
}
