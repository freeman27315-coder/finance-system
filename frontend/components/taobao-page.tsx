"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ListOrdered,
  Plus,
  RefreshCcw,
  ShoppingBag,
  Wallet
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createTaobaoAccount,
  creditTaobaoSettled,
  creditTaobaoUnsettled,
  debitTaobaoSettled,
  getTaobaoAccounts,
  getTaobaoTransactions
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { TaobaoAccount } from "@/types";

type MutationKind = "unsettled-credit" | "settled-credit" | "settled-debit";

const MUTATION_META: Record<MutationKind, { title: string; submit: string; success: string }> = {
  "unsettled-credit": { title: "未结算入账", submit: "确认入账", success: "入账成功" },
  "settled-credit": { title: "已结算入账", submit: "确认入账", success: "入账成功" },
  "settled-debit": { title: "已结算出账", submit: "确认出账", success: "出账成功" }
};

function formatDateTime(value: string) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

function SummaryCards({ accounts }: { accounts: TaobaoAccount[] }) {
  const unsettledTotal = accounts.reduce((sum, acc) => sum + acc.unsettledBalanceMinor, 0);
  const settledTotal = accounts.reduce((sum, acc) => sum + acc.settledBalanceMinor, 0);
  const accountCount = accounts.length;

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card className="border border-muted-foreground/30">
        <CardContent className="flex items-center justify-between gap-4 p-5">
          <div>
            <div className="text-sm text-muted-foreground">未结算总额</div>
            <div className="mt-1 tabular-nums text-2xl font-semibold text-muted-foreground">
              {formatMoney(unsettledTotal, "CNY")}
            </div>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Wallet className="h-5 w-5" aria-hidden="true" />
          </div>
        </CardContent>
      </Card>
      <Card className="border border-emerald-500/40">
        <CardContent className="flex items-center justify-between gap-4 p-5">
          <div>
            <div className="text-sm text-muted-foreground">已结算总额</div>
            <div className="mt-1 tabular-nums text-2xl font-semibold text-emerald-600">
              {formatMoney(settledTotal, "CNY")}
            </div>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
            <ArrowDownLeft className="h-5 w-5" aria-hidden="true" />
          </div>
        </CardContent>
      </Card>
      <Card className="border">
        <CardContent className="flex items-center justify-between gap-4 p-5">
          <div>
            <div className="text-sm text-muted-foreground">账号总数</div>
            <div className="mt-1 tabular-nums text-2xl font-semibold">{accountCount}</div>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
            <ShoppingBag className="h-5 w-5" aria-hidden="true" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateAccountModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) {
        throw new Error("账号名不能为空");
      }
      return createTaobaoAccount({
        name: name.trim(),
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taobao-accounts"] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>新建淘宝账号</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">账号名</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="账号名"
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
              {mutation.isPending ? "创建中..." : "创建"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MovementModal({
  account,
  kind,
  onClose
}: {
  account: TaobaoAccount;
  kind: MutationKind;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);
  const meta = MUTATION_META[kind];

  const mutation = useMutation({
    mutationFn: async () => {
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      const payload = {
        amount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      };
      if (kind === "unsettled-credit") {
        return creditTaobaoUnsettled(account.id, payload);
      }
      if (kind === "settled-credit") {
        return creditTaobaoSettled(account.id, payload);
      }
      return debitTaobaoSettled(account.id, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taobao-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-transactions", account.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : `${meta.title}失败`);
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>
            {meta.title} · {account.name}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">金额（CNY）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="金额"
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
              {mutation.isPending ? "提交中..." : meta.submit}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TransactionsModal({ account, onClose }: { account: TaobaoAccount; onClose: () => void }) {
  const { data: transactions = [], isFetching } = useQuery({
    queryKey: ["taobao-transactions", account.id],
    queryFn: () => getTaobaoTransactions(account.id)
  });

  const sorted = [...transactions].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-3xl">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>{account.name} · 流水</CardTitle>
            <Button variant="ghost" size="sm" onClick={onClose}>
              关闭
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>钱包</TableHead>
                <TableHead>方向</TableHead>
                <TableHead className="text-right">金额</TableHead>
                <TableHead>备注</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((tx) => {
                const isIn = tx.direction === "in";
                const isSettled = tx.walletScope === "settled";
                return (
                  <TableRow key={tx.id}>
                    <TableCell>
                      <Badge tone={isSettled ? "success" : "neutral"}>
                        {isSettled ? "已结算" : "未结算"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge tone={isIn ? "success" : "danger"}>{isIn ? "入账" : "出账"}</Badge>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums font-semibold",
                        isIn ? "text-green-600" : "text-red-600"
                      )}
                    >
                      {formatMoney(tx.amountMinor, "CNY")}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{tx.remark ?? "-"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(tx.createdAt)}</TableCell>
                  </TableRow>
                );
              })}
              {sorted.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
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

function AccountCard({
  account,
  onMovement,
  onTransactions
}: {
  account: TaobaoAccount;
  onMovement: (account: TaobaoAccount, kind: MutationKind) => void;
  onTransactions: (account: TaobaoAccount) => void;
}) {
  return (
    <Card className="border">
      <CardHeader>
        <CardTitle className="text-base">{account.name}</CardTitle>
        {account.remark ? (
          <div className="text-sm text-muted-foreground">{account.remark}</div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-md border border-muted-foreground/20 bg-muted/40 p-3">
            <div className="text-xs text-muted-foreground">未结算</div>
            <div className="mt-1 tabular-nums text-lg font-semibold text-muted-foreground">
              {formatMoney(account.unsettledBalanceMinor, "CNY")}
            </div>
          </div>
          <div className="rounded-md border border-emerald-500/40 bg-emerald-50/50 p-3">
            <div className="text-xs text-emerald-700">已结算</div>
            <div className="mt-1 tabular-nums text-lg font-semibold text-emerald-600">
              {formatMoney(account.settledBalanceMinor, "CNY")}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => onMovement(account, "unsettled-credit")}>
            <ArrowDownLeft className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            未结算入账
          </Button>
          <Button size="sm" variant="outline" onClick={() => onMovement(account, "settled-credit")}>
            <ArrowDownLeft className="h-4 w-4 text-green-600" aria-hidden="true" />
            已结算入账
          </Button>
          <Button size="sm" variant="outline" onClick={() => onMovement(account, "settled-debit")}>
            <ArrowUpRight className="h-4 w-4 text-red-600" aria-hidden="true" />
            已结算出账
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onTransactions(account)}>
            <ListOrdered className="h-4 w-4" aria-hidden="true" />
            查看流水
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function TaobaoPage() {
  const [showCreate, setShowCreate] = useState(false);
  const [movementTarget, setMovementTarget] = useState<{ account: TaobaoAccount; kind: MutationKind } | null>(null);
  const [transactionsTarget, setTransactionsTarget] = useState<TaobaoAccount | null>(null);

  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["taobao-accounts"],
    queryFn: getTaobaoAccounts
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">淘宝账号</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            管理淘宝账号的未结算 / 已结算两个钱包，记录入出账流水。
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className="h-4 w-4" aria-hidden="true" />
            刷新
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新建账号
          </Button>
        </div>
      </div>

      <SummaryCards accounts={accounts} />

      {accounts.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            {isFetching ? "加载中..." : "暂无淘宝账号，点击右上角「+ 新建账号」开始"}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {accounts.map((account) => (
            <AccountCard
              key={account.id}
              account={account}
              onMovement={(acc, kind) => setMovementTarget({ account: acc, kind })}
              onTransactions={setTransactionsTarget}
            />
          ))}
        </div>
      )}

      {showCreate ? <CreateAccountModal onClose={() => setShowCreate(false)} /> : null}
      {movementTarget ? (
        <MovementModal
          account={movementTarget.account}
          kind={movementTarget.kind}
          onClose={() => setMovementTarget(null)}
        />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal account={transactionsTarget} onClose={() => setTransactionsTarget(null)} />
      ) : null}
    </div>
  );
}
