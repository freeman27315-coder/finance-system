"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Gamepad2, Plus, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  consumeXboxAccount,
  createXboxAccount,
  getXboxAccounts,
  getXboxSummary,
  getXboxTransactions,
  rechargeXboxAccount
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { XboxAccount, XboxCountry, XboxTransaction } from "@/types";

type XboxAction = "recharge" | "consume";

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

function XboxSummaryCards({ country }: { country: XboxCountry }) {
  const { data } = useQuery({
    queryKey: ["xbox-summary"],
    queryFn: getXboxSummary
  });
  const localCurrency = country === "US" ? "USD" : "GBP";
  const rmbCost = country === "US" ? data?.usRmbCostMinor ?? 0 : data?.ukRmbCostMinor ?? 0;
  const localBalance = country === "US" ? data?.usLocalBalanceMinor ?? 0 : data?.ukLocalBalanceMinor ?? 0;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">{country} 累计 RMB 成本</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(rmbCost, "CNY")}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">{country} 本地余额</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">
            {formatMoney(localBalance, localCurrency)}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function XboxAccountForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [country, setCountry] = useState<XboxCountry>("US");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) {
        throw new Error("账户名称不能为空");
      }
      return createXboxAccount(name.trim(), country, remark.trim());
    },
    onSuccess: async () => {
      setName("");
      setRemark("");
      setMessage("XBOX 账户创建请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建失败")
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>新增 XBOX 账户</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input value={name} onChange={setName} placeholder="账户名称" />
        <select
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          value={country}
          onChange={(event) => setCountry(event.target.value as XboxCountry)}
        >
          <option value="US">美国 USD</option>
          <option value="UK">英国 GBP</option>
        </select>
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

function XboxMovementForm({ accounts, selectedAccountId }: { accounts: XboxAccount[]; selectedAccountId: string }) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(selectedAccountId);
  const [action, setAction] = useState<XboxAction>("recharge");
  const [rmbAmount, setRmbAmount] = useState("");
  const [localAmount, setLocalAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const activeAccountId = accountId || selectedAccountId || accounts[0]?.id || "";

  const mutation = useMutation({
    mutationFn: () => {
      if (!activeAccountId) {
        throw new Error("请选择 XBOX 账户");
      }
      if (!localAmount || Number(localAmount) <= 0) {
        throw new Error("本地金额必须大于 0");
      }
      if (action === "recharge") {
        if (!rmbAmount || Number(rmbAmount) <= 0) {
          throw new Error("RMB 成本必须大于 0");
        }
        return rechargeXboxAccount(activeAccountId, rmbAmount, localAmount);
      }
      return consumeXboxAccount(activeAccountId, localAmount, remark);
    },
    onSuccess: async () => {
      setRmbAmount("");
      setLocalAmount("");
      setRemark("");
      setMessage("XBOX 操作请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-transactions"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "操作失败")
  });

  if (accounts.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>充值 / 消费</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <select
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          value={activeAccountId}
          onChange={(event) => setAccountId(event.target.value)}
        >
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} / {account.currency}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 rounded-md border border-border p-1">
          {(["recharge", "consume"] as XboxAction[]).map((item) => (
            <button
              key={item}
              className={cn(
                "h-8 rounded text-sm font-medium text-muted-foreground",
                action === item && "bg-muted text-foreground"
              )}
              type="button"
              onClick={() => setAction(item)}
            >
              {item === "recharge" ? "充值" : "消费"}
            </button>
          ))}
        </div>
        {action === "recharge" ? (
          <Input value={rmbAmount} onChange={setRmbAmount} placeholder="RMB 成本" type="number" />
        ) : null}
        <Input value={localAmount} onChange={setLocalAmount} placeholder="本地金额" type="number" />
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {action === "recharge" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
          提交{action === "recharge" ? "充值" : "消费"}
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function XboxAccountsTable({
  accounts,
  selectedAccountId,
  onSelect
}: {
  accounts: XboxAccount[];
  selectedAccountId: string;
  onSelect: (accountId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>账户列表</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账户</TableHead>
              <TableHead>地区</TableHead>
              <TableHead className="text-right">RMB 成本</TableHead>
              <TableHead className="text-right">本地余额</TableHead>
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
                <TableCell>
                  <Badge tone="transfer">{account.country === "US" ? "美国 USD" : "英国 GBP"}</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(account.rmbCostMinor, "CNY")}
                </TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(account.localBalanceMinor, account.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function XboxTransactionsTable({ transactions }: { transactions: XboxTransaction[] }) {
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
              <TableHead>类型</TableHead>
              <TableHead>账户</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">RMB 成本</TableHead>
              <TableHead className="text-right">本地金额</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transactions.map((transaction) => (
              <TableRow
                key={transaction.id}
                className={transaction.type === "recharge" ? "border-l-2 border-l-emerald-500" : "border-l-2 border-l-red-500"}
              >
                <TableCell className="text-muted-foreground">
                  {transaction.createdAt ? new Date(transaction.createdAt).toLocaleString("zh-CN") : "-"}
                </TableCell>
                <TableCell>
                  <Badge tone={transaction.type === "recharge" ? "success" : "danger"}>
                    {transaction.type === "recharge" ? "充值" : "消费"}
                  </Badge>
                </TableCell>
                <TableCell>{transaction.accountName}</TableCell>
                <TableCell className="text-muted-foreground">{transaction.remark || "-"}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {transaction.rmbAmountMinor ? formatMoney(transaction.rmbAmountMinor, "CNY") : "-"}
                </TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(
                    transaction.type === "recharge" ? transaction.localAmountMinor : -transaction.localAmountMinor,
                    transaction.currency,
                    { accounting: transaction.type === "consume", signed: transaction.type === "recharge" }
                  )}
                </TableCell>
              </TableRow>
            ))}
            {transactions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  当前账户暂无流水
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function XboxPage() {
  const [country, setCountry] = useState<XboxCountry>("US");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: getXboxAccounts
  });
  const scopedAccounts = useMemo(() => accounts.filter((account) => account.country === country), [accounts, country]);
  const selectedAccount = scopedAccounts.find((account) => account.id === selectedAccountId) ?? scopedAccounts[0];
  const { data: transactions = [] } = useQuery({
    queryKey: ["xbox-transactions", selectedAccount?.id],
    queryFn: () => getXboxTransactions(selectedAccount as XboxAccount),
    enabled: Boolean(selectedAccount)
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">XBOX 账户</h2>
          <p className="mt-1 text-sm text-muted-foreground">美国 USD、英国 GBP 账户的 RMB 成本、本地余额和流水。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      <div className="grid gap-2 rounded-lg border border-border bg-card p-2 md:grid-cols-2">
        {(["US", "UK"] as XboxCountry[]).map((item) => (
          <button
            key={item}
            className={cn("rounded-md px-4 py-3 text-left hover:bg-muted", country === item && "bg-muted")}
            type="button"
            onClick={() => {
              setCountry(item);
              setSelectedAccountId("");
            }}
          >
            <div className="flex items-center gap-2 font-semibold">
              <Gamepad2 className="h-4 w-4" />
              {item === "US" ? "美国 USD" : "英国 GBP"}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">账户余额、RMB 成本和交易流水</div>
          </button>
        ))}
      </div>

      <XboxSummaryCards country={country} />
      <div className="grid gap-3 xl:grid-cols-[0.8fr_1.2fr]">
        <XboxAccountForm />
        <XboxMovementForm accounts={scopedAccounts} selectedAccountId={selectedAccount?.id ?? ""} />
      </div>
      <XboxAccountsTable
        accounts={scopedAccounts}
        selectedAccountId={selectedAccount?.id ?? ""}
        onSelect={setSelectedAccountId}
      />
      <XboxTransactionsTable transactions={transactions} />
    </div>
  );
}
