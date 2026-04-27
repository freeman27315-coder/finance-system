"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Plus, RefreshCcw, ShoppingBag } from "lucide-react";
import { useMemo, useState } from "react";
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
import { formatMoney, sumMinor } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { TaobaoAccount, TaobaoTransaction } from "@/types";

type TaobaoAction = "unsettled-credit" | "settled-credit" | "settled-debit";

function Input({
  value,
  onChange,
  placeholder,
  type = "text"
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
}) {
  return (
    <input
      className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      type={type}
      min={type === "number" ? "0" : undefined}
      step={type === "number" ? "0.01" : undefined}
    />
  );
}

function SummaryCards({ accounts }: { accounts: TaobaoAccount[] }) {
  const unsettled = sumMinor(accounts.map((account) => account.unsettledBalanceMinor));
  const settled = sumMinor(accounts.map((account) => account.settledBalanceMinor));

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">未结算</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(unsettled, "CNY")}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">已结算</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(settled, "CNY")}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">账户数</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{accounts.length}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateAccountForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) {
        throw new Error("淘宝账户名称不能为空");
      }
      return createTaobaoAccount(name.trim(), remark.trim());
    },
    onSuccess: async () => {
      setName("");
      setRemark("");
      setMessage("淘宝账户创建请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["taobao-accounts"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建失败")
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>新增淘宝账户</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input value={name} onChange={setName} placeholder="账户名称" />
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <Plus className="h-4 w-4" />
          创建账户
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function MovementForm({ accounts, selectedAccountId }: { accounts: TaobaoAccount[]; selectedAccountId: string }) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(selectedAccountId);
  const [action, setAction] = useState<TaobaoAction>("unsettled-credit");
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const activeAccountId = accountId || selectedAccountId || accounts[0]?.id || "";

  const mutation = useMutation({
    mutationFn: () => {
      if (!activeAccountId) {
        throw new Error("请选择淘宝账户");
      }
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      if (action === "unsettled-credit") {
        return creditTaobaoUnsettled(activeAccountId, amount, remark);
      }
      if (action === "settled-credit") {
        return creditTaobaoSettled(activeAccountId, amount, remark);
      }
      return debitTaobaoSettled(activeAccountId, amount, remark);
    },
    onSuccess: async () => {
      setAmount("");
      setRemark("");
      setMessage("淘宝资金操作请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["taobao-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-transactions"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "操作失败")
  });

  if (accounts.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>资金操作</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <select
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          value={activeAccountId}
          onChange={(event) => setAccountId(event.target.value)}
        >
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
        <div className="grid gap-2 rounded-md border border-border p-1 md:grid-cols-3">
          {[
            ["unsettled-credit", "未结算入账"],
            ["settled-credit", "已结算入账"],
            ["settled-debit", "已结算出账"]
          ].map(([id, label]) => (
            <button
              key={id}
              className={cn(
                "h-8 rounded text-sm font-medium text-muted-foreground",
                action === id && "bg-muted text-foreground"
              )}
              type="button"
              onClick={() => setAction(id as TaobaoAction)}
            >
              {label}
            </button>
          ))}
        </div>
        <Input value={amount} onChange={setAmount} placeholder="金额" type="number" />
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {action === "settled-debit" ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownLeft className="h-4 w-4" />}
          提交操作
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function AccountsTable({
  accounts,
  selectedAccountId,
  onSelect
}: {
  accounts: TaobaoAccount[];
  selectedAccountId: string;
  onSelect: (accountId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>淘宝账户</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账户</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">未结算</TableHead>
              <TableHead className="text-right">已结算</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.map((account) => (
              <TableRow
                key={account.id}
                className={cn("cursor-pointer", selectedAccountId === account.id && "bg-muted/70")}
                onClick={() => onSelect(account.id)}
              >
                <TableCell className="font-medium">{account.name}</TableCell>
                <TableCell className="text-muted-foreground">{account.remark || "-"}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(account.unsettledBalanceMinor, "CNY")}
                </TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(account.settledBalanceMinor, "CNY")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function TransactionsTable({ transactions }: { transactions: TaobaoTransaction[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>交易流水</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead>
              <TableHead>钱包范围</TableHead>
              <TableHead>方向</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">金额</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transactions.map((transaction) => (
              <TableRow
                key={transaction.id}
                className={transaction.direction === "in" ? "border-l-2 border-l-emerald-500" : "border-l-2 border-l-red-500"}
              >
                <TableCell className="text-muted-foreground">
                  {transaction.createdAt ? new Date(transaction.createdAt).toLocaleString("zh-CN") : "-"}
                </TableCell>
                <TableCell>
                  <Badge tone={transaction.walletScope === "unsettled" ? "transfer" : "neutral"}>
                    {transaction.walletScope === "unsettled" ? "未结算" : "已结算"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge tone={transaction.direction === "in" ? "success" : "danger"}>
                    {transaction.direction === "in" ? "入账" : "出账"}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{transaction.remark || "-"}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(
                    transaction.direction === "in" ? transaction.amountMinor : -transaction.amountMinor,
                    "CNY",
                    { accounting: transaction.direction === "out", signed: transaction.direction === "in" }
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function TaobaoPage() {
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["taobao-accounts"],
    queryFn: getTaobaoAccounts
  });
  const selectedAccount = accounts.find((account) => account.id === selectedAccountId) ?? accounts[0];
  const { data: transactions = [] } = useQuery({
    queryKey: ["taobao-transactions", selectedAccount?.id],
    queryFn: () => getTaobaoTransactions(selectedAccount as TaobaoAccount),
    enabled: Boolean(selectedAccount)
  });
  const transactionCount = useMemo(() => transactions.length, [transactions]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">淘宝资金</h2>
          <p className="mt-1 text-sm text-muted-foreground">淘宝未结算、已结算钱包和资金流水。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      <SummaryCards accounts={accounts} />
      <div className="grid gap-3 xl:grid-cols-[0.8fr_1.2fr]">
        <CreateAccountForm />
        <MovementForm accounts={accounts} selectedAccountId={selectedAccount?.id ?? ""} />
      </div>
      <div className="grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
        <AccountsTable accounts={accounts} selectedAccountId={selectedAccount?.id ?? ""} onSelect={setSelectedAccountId} />
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">当前账户流水数</div>
              <div className="mt-2 tabular-nums text-3xl font-semibold">{transactionCount}</div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
              <ShoppingBag className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>
      </div>
      <TransactionsTable transactions={transactions} />
    </div>
  );
}
