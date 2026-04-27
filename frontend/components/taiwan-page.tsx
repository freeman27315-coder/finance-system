"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Landmark, RefreshCcw } from "lucide-react";
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
import type { TaiwanTransaction, TaiwanWallet } from "@/types";

type TaiwanAction = "credit" | "debit";

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

function SummaryCards() {
  const { data } = useQuery({
    queryKey: ["taiwan-summary"],
    queryFn: getTaiwanSummary
  });

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">TWD 总余额</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">
            {formatMoney(data?.totalBalanceMinor ?? 0, "TWD")}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">钱包数量</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{data?.walletCount ?? 0}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function MovementForm({ wallets, selectedWalletId }: { wallets: TaiwanWallet[]; selectedWalletId: string }) {
  const queryClient = useQueryClient();
  const [walletId, setWalletId] = useState(selectedWalletId);
  const [action, setAction] = useState<TaiwanAction>("credit");
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const activeWalletId = walletId || selectedWalletId || wallets[0]?.id || "";

  const mutation = useMutation({
    mutationFn: () => {
      if (!activeWalletId) {
        throw new Error("请选择台湾钱包");
      }
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      return action === "credit"
        ? creditTaiwanWallet(activeWalletId, amount, remark)
        : debitTaiwanWallet(activeWalletId, amount, remark);
    },
    onSuccess: async () => {
      setAmount("");
      setRemark("");
      setMessage("台湾钱包操作请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-transactions"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "操作失败")
  });

  if (wallets.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>入账 / 出账</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <select
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          value={activeWalletId}
          onChange={(event) => setWalletId(event.target.value)}
        >
          {wallets.map((wallet) => (
            <option key={wallet.id} value={wallet.id}>
              {wallet.name}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 rounded-md border border-border p-1">
          {(["credit", "debit"] as TaiwanAction[]).map((item) => (
            <button
              key={item}
              className={cn(
                "h-8 rounded text-sm font-medium text-muted-foreground",
                action === item && "bg-muted text-foreground"
              )}
              type="button"
              onClick={() => setAction(item)}
            >
              {item === "credit" ? "入账" : "出账"}
            </button>
          ))}
        </div>
        <Input value={amount} onChange={setAmount} placeholder="TWD 金额" type="number" />
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {action === "credit" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
          提交{action === "credit" ? "入账" : "出账"}
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function WalletTable({
  wallets,
  selectedWalletId,
  onSelect
}: {
  wallets: TaiwanWallet[];
  selectedWalletId: string;
  onSelect: (walletId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>台湾钱包</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>钱包</TableHead>
              <TableHead>币种</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead className="text-right">余额</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {wallets.map((wallet) => (
              <TableRow
                key={wallet.id}
                className={cn("cursor-pointer", selectedWalletId === wallet.id && "bg-muted/70")}
                onClick={() => onSelect(wallet.id)}
              >
                <TableCell className="font-medium">{wallet.name}</TableCell>
                <TableCell>
                  <Badge tone="transfer">TWD</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {wallet.createdAt ? new Date(wallet.createdAt).toLocaleDateString("zh-CN") : "-"}
                </TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(wallet.balanceMinor, "TWD")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function TransactionsTable({ transactions }: { transactions: TaiwanTransaction[] }) {
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
              <TableHead>方向</TableHead>
              <TableHead>钱包</TableHead>
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
                  <Badge tone={transaction.direction === "in" ? "success" : "danger"}>
                    {transaction.direction === "in" ? "入账" : "出账"}
                  </Badge>
                </TableCell>
                <TableCell>{transaction.walletName}</TableCell>
                <TableCell className="text-muted-foreground">{transaction.remark || "-"}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(
                    transaction.direction === "in" ? transaction.amountMinor : -transaction.amountMinor,
                    "TWD",
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

export function TaiwanPage() {
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const { data: wallets = [], isFetching, refetch } = useQuery({
    queryKey: ["taiwan-wallets"],
    queryFn: getTaiwanWallets
  });
  const selectedWallet = wallets.find((wallet) => wallet.id === selectedWalletId) ?? wallets[0];
  const { data: transactions = [] } = useQuery({
    queryKey: ["taiwan-transactions", selectedWallet?.id],
    queryFn: () => getTaiwanTransactions(selectedWallet as TaiwanWallet),
    enabled: Boolean(selectedWallet)
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">台湾钱包</h2>
          <p className="mt-1 text-sm text-muted-foreground">8591余额、银行卡、超商代收金流余额和 TWD 流水。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      <SummaryCards />
      <div className="grid gap-3 xl:grid-cols-[1fr_0.8fr]">
        <WalletTable wallets={wallets} selectedWalletId={selectedWallet?.id ?? ""} onSelect={setSelectedWalletId} />
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">当前钱包</div>
              <div className="mt-2 text-2xl font-semibold">{selectedWallet?.name ?? "-"}</div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
              <Landmark className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>
      </div>
      <MovementForm wallets={wallets} selectedWalletId={selectedWallet?.id ?? ""} />
      <TransactionsTable transactions={transactions} />
    </div>
  );
}
