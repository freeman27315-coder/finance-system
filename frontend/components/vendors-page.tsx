"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Plus,
  RefreshCcw,
  Wallet
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createVendor,
  getAssetWallets,
  getVendorTransactions,
  getVendors,
  payVendor
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Vendor, VendorTransaction, WalletBalance } from "@/types";

function flattenLeafAssetWallets(wallets: WalletBalance[]): WalletBalance[] {
  const result: WalletBalance[] = [];
  const walk = (list: WalletBalance[]) => {
    for (const wallet of list) {
      if (wallet.children && wallet.children.length > 0) {
        walk(wallet.children);
      }
      const isAsset = wallet.type === "ASSET_RMB" || wallet.type === "ASSET_USDT";
      if (isAsset && !wallet.isGroup && wallet.deletedAt == null) {
        result.push(wallet);
      }
    }
  };
  walk(wallets);
  return result;
}

function balanceLabel(balanceMinor: number): { text: string; tone: "danger" | "success" | "neutral" } {
  if (balanceMinor > 0) {
    return { text: `我们欠 ${formatMoney(balanceMinor, "CNY")}`, tone: "danger" };
  }
  if (balanceMinor < 0) {
    return { text: `已预付 ${formatMoney(balanceMinor, "CNY", { accounting: true })}`, tone: "success" };
  }
  return { text: "已结清", tone: "neutral" };
}

function CreateVendorModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) {
        throw new Error("供应商名称不能为空");
      }
      return createVendor({
        name: name.trim(),
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["vendors"] });
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
          <CardTitle>新增供应商</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">供应商名称</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="供应商名称"
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

function PayVendorModal({ vendor, onClose }: { vendor: Vendor; onClose: () => void }) {
  const queryClient = useQueryClient();

  const { data: assetWallets = [], isLoading: walletsLoading } = useQuery({
    queryKey: ["asset-wallets"],
    queryFn: getAssetWallets
  });

  const leafAssetWallets = useMemo(
    () => flattenLeafAssetWallets(assetWallets),
    [assetWallets]
  );

  const [fromWalletId, setFromWalletId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [exchangeRate, setExchangeRate] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!fromWalletId && leafAssetWallets.length > 0) {
      setFromWalletId(leafAssetWallets[0].id);
    }
  }, [leafAssetWallets, fromWalletId]);

  const fromWallet = leafAssetWallets.find((w) => w.id === fromWalletId);
  const isCrossCurrency = fromWallet ? fromWallet.currency !== "CNY" : false;

  const mutation = useMutation({
    mutationFn: async () => {
      if (!fromWalletId) {
        throw new Error("请选择付款钱包");
      }
      const numAmount = Number.parseFloat(amount);
      if (!amount || Number.isNaN(numAmount) || numAmount <= 0) {
        throw new Error("金额必须大于 0");
      }
      if (isCrossCurrency) {
        const rate = Number.parseFloat(exchangeRate);
        if (!exchangeRate || Number.isNaN(rate) || rate <= 0) {
          throw new Error("跨币种付款必须填写汇率");
        }
      }
      return payVendor(vendor.id, {
        fromWalletId,
        amount,
        exchangeRate: isCrossCurrency ? exchangeRate : undefined,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["vendors"] });
      await queryClient.invalidateQueries({ queryKey: ["vendor-transactions", vendor.id] });
      await queryClient.invalidateQueries({ queryKey: ["asset-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "付款失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>用资产钱包付款 · {vendor.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">付款钱包</div>
            {walletsLoading ? (
              <div className="text-sm text-muted-foreground">加载中...</div>
            ) : leafAssetWallets.length === 0 ? (
              <div className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
                暂无可用资产钱包
              </div>
            ) : (
              <select
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={fromWalletId}
                onChange={(event) => setFromWalletId(event.target.value)}
              >
                {leafAssetWallets.map((wallet) => (
                  <option key={wallet.id} value={wallet.id}>
                    {wallet.name} ({wallet.currency} · 余额 {formatMoney(wallet.balanceMinor, wallet.currency)})
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">
              金额（{fromWallet?.currency ?? "CNY"}）
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="付款金额"
              type="number"
              min="0"
              step="0.01"
            />
          </div>
          {isCrossCurrency ? (
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">
                汇率（1 {fromWallet?.currency} = ? CNY）
              </div>
              <input
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={exchangeRate}
                onChange={(event) => setExchangeRate(event.target.value)}
                placeholder="例如 7.2"
                type="number"
                min="0"
                step="0.0001"
              />
            </div>
          ) : null}
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
            <Button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || leafAssetWallets.length === 0}
            >
              {mutation.isPending ? "付款中..." : "确认付款"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function VendorList({
  vendors,
  selectedVendorId,
  onSelect,
  onCreate
}: {
  vendors: Vendor[];
  selectedVendorId: string;
  onSelect: (vendorId: string) => void;
  onCreate: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>供应商</CardTitle>
          <Button size="sm" onClick={onCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新增供应商
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {vendors.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            暂无供应商，点击右上角「新增供应商」开始
          </div>
        ) : (
          vendors.map((vendor) => {
            const label = balanceLabel(vendor.balanceMinor);
            return (
              <button
                key={vendor.id}
                type="button"
                className={cn(
                  "w-full rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:bg-muted/60",
                  selectedVendorId === vendor.id && "bg-muted"
                )}
                onClick={() => onSelect(vendor.id)}
              >
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <span className="font-medium">{vendor.name}</span>
                </div>
                {vendor.remark ? (
                  <div className="mt-1 text-xs text-muted-foreground">{vendor.remark}</div>
                ) : null}
                <div className="mt-2">
                  <Badge tone={label.tone}>{label.text}</Badge>
                </div>
              </button>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

function VendorDetail({
  vendor,
  transactions,
  onPay
}: {
  vendor: Vendor | null;
  transactions: VendorTransaction[];
  onPay: () => void;
}) {
  if (!vendor) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>供应商详情</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
            请先在左侧选中或新增供应商
          </div>
        </CardContent>
      </Card>
    );
  }

  const balanceColor =
    vendor.balanceMinor > 0
      ? "text-red-600"
      : vendor.balanceMinor < 0
        ? "text-green-600"
        : "text-muted-foreground";
  const label = balanceLabel(vendor.balanceMinor);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{vendor.name}</CardTitle>
            {vendor.remark ? (
              <div className="mt-1 text-sm text-muted-foreground">{vendor.remark}</div>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-border bg-card p-5">
          <div className="text-sm text-muted-foreground">当前余额</div>
          <div className={cn("mt-2 tabular-nums text-3xl font-semibold", balanceColor)}>
            {formatMoney(vendor.balanceMinor, "CNY", {
              accounting: vendor.balanceMinor < 0,
              signed: vendor.balanceMinor > 0
            })}
          </div>
          <div className="mt-2">
            <Badge tone={label.tone}>{label.text}</Badge>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onPay}>
            <Wallet className="h-4 w-4" aria-hidden="true" />
            用资产钱包付款
          </Button>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium text-muted-foreground">流水（倒序）</div>
          {transactions.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
              暂无流水
            </div>
          ) : (
            <div className="divide-y divide-border rounded-md border border-border">
              {transactions.map((tx) => {
                const isIn = tx.direction === "in";
                return (
                  <div key={tx.id} className="flex items-start justify-between gap-3 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge tone={isIn ? "danger" : "success"}>
                          {isIn ? "+" : "-"} {isIn ? "欠款增加" : "欠款减少"}
                        </Badge>
                        <span
                          className={cn(
                            "tabular-nums font-semibold",
                            isIn ? "text-red-600" : "text-green-600"
                          )}
                        >
                          {isIn ? "+" : "-"}
                          {formatMoney(tx.amountMinor, "CNY")}
                        </span>
                      </div>
                      {tx.remark ? (
                        <div className="mt-1 truncate text-xs text-muted-foreground">{tx.remark}</div>
                      ) : null}
                    </div>
                    <div className="shrink-0 text-xs text-muted-foreground">
                      {tx.createdAt ? tx.createdAt.replace("T", " ").slice(0, 16) : "-"}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function VendorsPage() {
  const [selectedVendorId, setSelectedVendorId] = useState("");
  const [showCreateVendor, setShowCreateVendor] = useState(false);
  const [showPay, setShowPay] = useState(false);

  const { data: vendors = [], isFetching, refetch } = useQuery({
    queryKey: ["vendors"],
    queryFn: getVendors
  });

  useEffect(() => {
    if (vendors.length === 0) {
      if (selectedVendorId !== "") {
        setSelectedVendorId("");
      }
      return;
    }
    if (!vendors.find((vendor) => vendor.id === selectedVendorId)) {
      setSelectedVendorId(vendors[0].id);
    }
  }, [vendors, selectedVendorId]);

  const selectedVendor = vendors.find((vendor) => vendor.id === selectedVendorId) ?? null;

  const { data: transactions = [] } = useQuery({
    queryKey: ["vendor-transactions", selectedVendor?.id ?? ""],
    queryFn: () =>
      selectedVendor ? getVendorTransactions(selectedVendor.id) : Promise.resolve([]),
    enabled: Boolean(selectedVendor)
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">供应商</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            每个供应商对应一个 RMB 钱包：余额 &gt; 0 表示我们欠对方，余额 &lt; 0 表示已预付。
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[0.9fr_1.6fr]">
        <VendorList
          vendors={vendors}
          selectedVendorId={selectedVendor?.id ?? ""}
          onSelect={setSelectedVendorId}
          onCreate={() => setShowCreateVendor(true)}
        />
        <VendorDetail
          vendor={selectedVendor}
          transactions={transactions}
          onPay={() => setShowPay(true)}
        />
      </div>

      {showCreateVendor ? (
        <CreateVendorModal onClose={() => setShowCreateVendor(false)} />
      ) : null}
      {showPay && selectedVendor ? (
        <PayVendorModal vendor={selectedVendor} onClose={() => setShowPay(false)} />
      ) : null}
    </div>
  );
}
