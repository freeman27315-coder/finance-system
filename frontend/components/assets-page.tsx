"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, FolderPlus, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createAssetSubWallet,
  creditAssetWallet,
  debitAssetWallet,
  getAssetTransactions,
  getAssetWallets
} from "@/lib/api";
import { formatMoney, sumMinor } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { AssetTransaction, Currency, WalletBalance } from "@/types";

type AssetTab = "CNY" | "USDT";
type MovementMode = "credit" | "debit";

const tabs: { id: AssetTab; label: string; description: string }[] = [
  { id: "CNY", label: "RMB", description: "CNY 主钱包与子钱包" },
  { id: "USDT", label: "USDT", description: "USDT 主钱包与子钱包" }
];

function WalletSelect({
  wallets,
  value,
  onChange
}: {
  wallets: WalletBalance[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <select
      className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {wallets.map((wallet) => (
        <option key={wallet.id} value={wallet.id}>
          {wallet.name}
        </option>
      ))}
    </select>
  );
}

function TextInput({
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

function AssetSummaryCards({ wallets, currency }: { wallets: WalletBalance[]; currency: Currency }) {
  const rootWallets = wallets.filter((wallet) => !wallet.parentId);
  const subWallets = wallets.filter((wallet) => wallet.parentId);
  const total = sumMinor(wallets.map((wallet) => wallet.balanceMinor));

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">{currency} 总余额</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(total, currency)}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">主钱包</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{rootWallets.length}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">子钱包</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{subWallets.length}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function AssetActions({ wallets }: { wallets: WalletBalance[] }) {
  const queryClient = useQueryClient();
  const [selectedWalletId, setSelectedWalletId] = useState(wallets[0]?.id ?? "");
  const [mode, setMode] = useState<MovementMode>("credit");
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [subWalletName, setSubWalletName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const selectedWallet = wallets.find((wallet) => wallet.id === selectedWalletId) ?? wallets[0];

  const movementMutation = useMutation({
    mutationFn: async () => {
      if (!selectedWallet) {
        throw new Error("请选择钱包");
      }
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      return mode === "credit"
        ? creditAssetWallet(selectedWallet.id, amount, remark)
        : debitAssetWallet(selectedWallet.id, amount, remark);
    },
    onSuccess: async () => {
      setMessage("操作已提交");
      setAmount("");
      setRemark("");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["asset-transactions"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "操作失败");
    }
  });

  const subWalletMutation = useMutation({
    mutationFn: async () => {
      if (!selectedWallet) {
        throw new Error("请选择主钱包");
      }
      if (!subWalletName.trim()) {
        throw new Error("子钱包名称不能为空");
      }
      return createAssetSubWallet(selectedWallet.id, subWalletName.trim());
    },
    onSuccess: async () => {
      setMessage("子钱包创建请求已提交");
      setSubWalletName("");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "创建失败");
    }
  });

  if (wallets.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
      <Card>
        <CardHeader>
          <CardTitle>入账 / 出账</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <WalletSelect wallets={wallets} value={selectedWallet?.id ?? ""} onChange={setSelectedWalletId} />
            <div className="grid grid-cols-2 rounded-md border border-border p-1">
              {(["credit", "debit"] as MovementMode[]).map((item) => (
                <button
                  key={item}
                  className={cn(
                    "flex h-8 items-center justify-center gap-2 rounded text-sm font-medium text-muted-foreground",
                    mode === item && "bg-muted text-foreground"
                  )}
                  type="button"
                  onClick={() => setMode(item)}
                >
                  {item === "credit" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
                  {item === "credit" ? "入账" : "出账"}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <TextInput value={amount} onChange={setAmount} placeholder="金额" type="number" />
            <TextInput value={remark} onChange={setRemark} placeholder="备注" />
          </div>
          <Button onClick={() => movementMutation.mutate()} disabled={movementMutation.isPending}>
            {mode === "credit" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
            提交{mode === "credit" ? "入账" : "出账"}
          </Button>
          {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>新增子钱包</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <WalletSelect wallets={wallets} value={selectedWallet?.id ?? ""} onChange={setSelectedWalletId} />
          <TextInput value={subWalletName} onChange={setSubWalletName} placeholder="子钱包名称" />
          <Button variant="outline" onClick={() => subWalletMutation.mutate()} disabled={subWalletMutation.isPending}>
            <FolderPlus className="h-4 w-4" />
            创建子钱包
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function AssetWalletTable({
  wallets,
  selectedWalletId,
  onSelect
}: {
  wallets: WalletBalance[];
  selectedWalletId: string;
  onSelect: (walletId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>钱包列表</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>钱包</TableHead>
              <TableHead>层级</TableHead>
              <TableHead>币种</TableHead>
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
                  <Badge tone={wallet.parentId ? "transfer" : "neutral"}>{wallet.parentId ? "子钱包" : "主钱包"}</Badge>
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{wallet.currency}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(wallet.balanceMinor, wallet.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function AssetTransactionTable({ transactions }: { transactions: AssetTransaction[] }) {
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
                <TableCell className="text-muted-foreground">{transaction.remark ?? "-"}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(
                    transaction.direction === "in" ? transaction.amountMinor : -transaction.amountMinor,
                    transaction.currency,
                    { accounting: transaction.direction === "out", signed: transaction.direction === "in" }
                  )}
                </TableCell>
              </TableRow>
            ))}
            {transactions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  当前钱包暂无流水
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function AssetsPage() {
  const [activeTab, setActiveTab] = useState<AssetTab>("CNY");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const { data: wallets = [], isFetching, refetch } = useQuery({
    queryKey: ["assets"],
    queryFn: getAssetWallets
  });

  const scopedWallets = useMemo(
    () => wallets.filter((wallet) => wallet.currency === activeTab),
    [activeTab, wallets]
  );
  const selectedWallet = scopedWallets.find((wallet) => wallet.id === selectedWalletId) ?? scopedWallets[0];
  const { data: transactions = [] } = useQuery({
    queryKey: ["asset-transactions", selectedWallet?.id],
    queryFn: () => getAssetTransactions(selectedWallet as WalletBalance),
    enabled: Boolean(selectedWallet)
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">资产钱包</h2>
          <p className="mt-1 text-sm text-muted-foreground">RMB 和 USDT 主钱包、子钱包、入账出账和交易流水。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      <div className="grid gap-2 rounded-lg border border-border bg-card p-2 md:grid-cols-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={cn(
              "rounded-md px-4 py-3 text-left transition-colors hover:bg-muted",
              activeTab === tab.id && "bg-muted"
            )}
            type="button"
            onClick={() => {
              setActiveTab(tab.id);
              setSelectedWalletId("");
            }}
          >
            <div className="font-semibold">{tab.label}</div>
            <div className="mt-1 text-sm text-muted-foreground">{tab.description}</div>
          </button>
        ))}
      </div>

      <AssetSummaryCards wallets={scopedWallets} currency={activeTab} />
      <AssetActions wallets={scopedWallets} />
      <AssetWalletTable
        wallets={scopedWallets}
        selectedWalletId={selectedWallet?.id ?? ""}
        onSelect={setSelectedWalletId}
      />
      <AssetTransactionTable transactions={transactions} />
    </div>
  );
}
