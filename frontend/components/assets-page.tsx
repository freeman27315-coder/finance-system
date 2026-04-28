"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  FolderPlus,
  List,
  RefreshCcw
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
  { id: "CNY", label: "RMB", description: "CNY 主钱包与子树结构" },
  { id: "USDT", label: "USDT", description: "USDT 主钱包与子树结构" }
];

function flattenLeafWallets(wallets: WalletBalance[]): WalletBalance[] {
  return wallets.flatMap((wallet) =>
    wallet.children && wallet.children.length > 0
      ? wallet.isGroup
        ? flattenLeafWallets(wallet.children)
        : [{ ...wallet, children: [] }, ...flattenLeafWallets(wallet.children)]
      : wallet.isGroup
        ? []
        : [{ ...wallet, children: [] }]
  );
}

function flattenGroupWallets(wallets: WalletBalance[]): WalletBalance[] {
  return wallets.flatMap((wallet) => [
    ...(wallet.isGroup ? [{ ...wallet }] : []),
    ...flattenGroupWallets(wallet.children ?? [])
  ]);
}

function collectGroupIds(wallets: WalletBalance[]): string[] {
  return wallets.flatMap((wallet) => [
    ...(wallet.isGroup ? [wallet.id] : []),
    ...collectGroupIds(wallet.children ?? [])
  ]);
}

function findWalletById(wallets: WalletBalance[], walletId: string): WalletBalance | undefined {
  for (const wallet of wallets) {
    if (wallet.id === walletId) {
      return wallet;
    }
    const childMatch = findWalletById(wallet.children ?? [], walletId);
    if (childMatch) {
      return childMatch;
    }
  }
  return undefined;
}

function AssetSummaryCards({ wallets, currency }: { wallets: WalletBalance[]; currency: Currency }) {
  const leafWallets = flattenLeafWallets(wallets);
  const groupWallets = flattenGroupWallets(wallets);
  const total = sumMinor(leafWallets.map((wallet) => wallet.balanceMinor));

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">{currency} 叶子总余额</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{formatMoney(total, currency)}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">分组节点</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{groupWallets.length}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5">
          <div className="text-sm text-muted-foreground">叶子钱包</div>
          <div className="mt-2 tabular-nums text-3xl font-semibold">{leafWallets.length}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function AssetActions({
  leafWallets,
  groupWallets,
  selectedWallet,
  selectedGroupId,
  mode,
  onModeChange,
  onSelectLeaf,
  onSelectGroup
}: {
  leafWallets: WalletBalance[];
  groupWallets: WalletBalance[];
  selectedWallet?: WalletBalance;
  selectedGroupId: string;
  mode: MovementMode;
  onModeChange: (mode: MovementMode) => void;
  onSelectLeaf: (walletId: string) => void;
  onSelectGroup: (walletId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [subWalletName, setSubWalletName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const selectedGroup = groupWallets.find((wallet) => wallet.id === selectedGroupId) ?? groupWallets[0];

  const movementMutation = useMutation({
    mutationFn: async () => {
      if (!selectedWallet) {
        throw new Error("请选择叶子钱包");
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
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["asset-transactions"] });
    },
    onError: (error) => {
      const text = error instanceof Error ? error.message : "操作失败";
      setMessage(text);
      window.alert(text);
    }
  });

  const subWalletMutation = useMutation({
    mutationFn: async () => {
      if (!selectedGroup) {
        throw new Error("请选择分组钱包");
      }
      if (!subWalletName.trim()) {
        throw new Error("子钱包名称不能为空");
      }
      return createAssetSubWallet(selectedGroup.id, subWalletName.trim());
    },
    onSuccess: async () => {
      setMessage("子钱包创建请求已提交");
      setSubWalletName("");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => {
      const text = error instanceof Error ? error.message : "创建失败";
      setMessage(text);
      window.alert(text);
    }
  });

  return (
    <div className="grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
      <Card>
        <CardHeader>
          <CardTitle>叶子钱包记账</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">当前钱包</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={selectedWallet?.id ?? ""}
              onChange={(event) => onSelectLeaf(event.target.value)}
            >
              {leafWallets.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {wallet.name}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 rounded-md border border-border p-1">
            {(["credit", "debit"] as MovementMode[]).map((item) => (
              <button
                key={item}
                className={cn(
                  "flex h-8 items-center justify-center gap-2 rounded text-sm font-medium text-muted-foreground",
                  mode === item && "bg-muted text-foreground"
                )}
                type="button"
                onClick={() => onModeChange(item)}
              >
                {item === "credit" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
                {item === "credit" ? "入账" : "出账"}
              </button>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="金额"
              type="number"
              min="0"
              step="0.01"
            />
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
              placeholder="备注"
            />
          </div>
          <Button onClick={() => movementMutation.mutate()} disabled={movementMutation.isPending || !selectedWallet}>
            {mode === "credit" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
            提交{mode === "credit" ? "入账" : "出账"}
          </Button>
          {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>给分组添加子钱包</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">目标分组</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={selectedGroup?.id ?? ""}
              onChange={(event) => onSelectGroup(event.target.value)}
            >
              {groupWallets.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {wallet.name}
                </option>
              ))}
            </select>
          </div>
          <input
            className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
            value={subWalletName}
            onChange={(event) => setSubWalletName(event.target.value)}
            placeholder="子钱包名称"
          />
          <Button
            variant="outline"
            onClick={() => subWalletMutation.mutate()}
            disabled={subWalletMutation.isPending || !selectedGroup}
          >
            <FolderPlus className="h-4 w-4" />
            添加子钱包
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function AssetTree({
  wallets,
  expandedIds,
  selectedWalletId,
  onToggle,
  onSelectLeaf,
  onSelectGroup,
  onShowTransactions
}: {
  wallets: WalletBalance[];
  expandedIds: Set<string>;
  selectedWalletId: string;
  onToggle: (walletId: string) => void;
  onSelectLeaf: (walletId: string, mode?: MovementMode) => void;
  onSelectGroup: (walletId: string) => void;
  onShowTransactions: (walletId: string) => void;
}) {
  const renderNode = (wallet: WalletBalance, depth: number) => {
    const hasChildren = Boolean(wallet.children?.length);
    const expanded = expandedIds.has(wallet.id);

    return (
      <div key={wallet.id} className="space-y-2">
        <div
          className={cn(
            "rounded-lg border border-border bg-card px-4 py-3",
            !wallet.isGroup && selectedWalletId === wallet.id && "bg-muted/60"
          )}
          style={{ marginLeft: depth * 20 }}
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <button
                className={cn(
                  "mt-0.5 flex h-6 w-6 items-center justify-center rounded text-muted-foreground",
                  !hasChildren && "opacity-30"
                )}
                type="button"
                disabled={!hasChildren}
                onClick={() => onToggle(wallet.id)}
              >
                {hasChildren && expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{wallet.name}</span>
                  {wallet.isGroup ? <Badge>汇总</Badge> : <Badge tone="transfer">叶子</Badge>}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{wallet.currency}</div>
              </div>
            </div>

            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="text-left tabular-nums text-lg font-semibold lg:min-w-[180px] lg:text-right">
                {formatMoney(wallet.balanceMinor, wallet.currency)}
              </div>
              <div className="flex flex-wrap gap-2">
                {wallet.isGroup ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onSelectGroup(wallet.id)}
                  >
                    <FolderPlus className="h-4 w-4" />
                    添加子钱包
                  </Button>
                ) : (
                  <>
                    <Button size="sm" onClick={() => onSelectLeaf(wallet.id, "credit")}>
                      <ArrowDownLeft className="h-4 w-4" />
                      入账
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => onSelectLeaf(wallet.id, "debit")}>
                      <ArrowUpRight className="h-4 w-4" />
                      出账
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onShowTransactions(wallet.id)}>
                      <List className="h-4 w-4" />
                      流水
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {hasChildren && expanded ? <div className="space-y-2">{wallet.children?.map((child) => renderNode(child, depth + 1))}</div> : null}
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>树状钱包结构</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{wallets.map((wallet) => renderNode(wallet, 0))}</CardContent>
    </Card>
  );
}

function AssetTransactionTable({ transactions }: { transactions: AssetTransaction[] }) {
  return (
    <Card id="asset-transactions">
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
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [movementMode, setMovementMode] = useState<MovementMode>("credit");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const { data: wallets = [], isFetching, refetch } = useQuery({
    queryKey: ["assets"],
    queryFn: getAssetWallets
  });

  const scopedWallets = useMemo(
    () => wallets.filter((wallet) => wallet.currency === activeTab),
    [activeTab, wallets]
  );
  const leafWallets = useMemo(() => flattenLeafWallets(scopedWallets), [scopedWallets]);
  const groupWallets = useMemo(() => flattenGroupWallets(scopedWallets), [scopedWallets]);

  useEffect(() => {
    const groupIds = collectGroupIds(scopedWallets);
    setExpandedIds(new Set(groupIds));
  }, [scopedWallets]);

  useEffect(() => {
    if (!leafWallets.find((wallet) => wallet.id === selectedWalletId)) {
      setSelectedWalletId(leafWallets[0]?.id ?? "");
    }
  }, [leafWallets, selectedWalletId]);

  useEffect(() => {
    if (!groupWallets.find((wallet) => wallet.id === selectedGroupId)) {
      setSelectedGroupId(groupWallets[0]?.id ?? "");
    }
  }, [groupWallets, selectedGroupId]);

  const selectedWallet = leafWallets.find((wallet) => wallet.id === selectedWalletId) ?? leafWallets[0];
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
          <p className="mt-1 text-sm text-muted-foreground">RMB 和 USDT 三层结构、分组折叠、叶子钱包记账和流水。</p>
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
              setSelectedGroupId("");
            }}
          >
            <div className="font-semibold">{tab.label}</div>
            <div className="mt-1 text-sm text-muted-foreground">{tab.description}</div>
          </button>
        ))}
      </div>

      <AssetSummaryCards wallets={scopedWallets} currency={activeTab} />
      <AssetTree
        wallets={scopedWallets}
        expandedIds={expandedIds}
        selectedWalletId={selectedWallet?.id ?? ""}
        onToggle={(walletId) =>
          setExpandedIds((current) => {
            const next = new Set(current);
            if (next.has(walletId)) {
              next.delete(walletId);
            } else {
              next.add(walletId);
            }
            return next;
          })
        }
        onSelectLeaf={(walletId, mode) => {
          setSelectedWalletId(walletId);
          if (mode) {
            setMovementMode(mode);
          }
        }}
        onSelectGroup={setSelectedGroupId}
        onShowTransactions={(walletId) => {
          setSelectedWalletId(walletId);
          document.getElementById("asset-transactions")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />
      <AssetActions
        leafWallets={leafWallets}
        groupWallets={groupWallets}
        selectedWallet={selectedWallet}
        selectedGroupId={selectedGroupId}
        mode={movementMode}
        onModeChange={setMovementMode}
        onSelectLeaf={setSelectedWalletId}
        onSelectGroup={setSelectedGroupId}
      />
      <AssetTransactionTable transactions={transactions} />
    </div>
  );
}
