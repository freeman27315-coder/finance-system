"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  ListOrdered,
  Pencil,
  Plus,
  RefreshCcw,
  Trash2,
  Wallet as WalletIcon
} from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createTaiwanWallet,
  creditTaiwanWallet,
  debitTaiwanWallet,
  deleteTaiwanWallet,
  getTaiwanSummary,
  getTaiwanTransactions,
  getTaiwanWallets,
  updateTaiwanWallet
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { TaiwanWallet } from "@/types";

// CEO 2026-05-18: 操作人名字存在 localStorage, 跨刷新保持
const OP_NAME_KEY = "taiwan-operator-name";
function getStoredOperatorName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(OP_NAME_KEY) ?? "";
}
function setStoredOperatorName(name: string) {
  if (typeof window === "undefined") return;
  if (name) localStorage.setItem(OP_NAME_KEY, name);
}

function formatDateTime(value: string) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

function SummaryHeader({
  total,
  count,
  isFetching,
  onRefresh,
  onCreateClick
}: {
  total: number;
  count: number;
  isFetching: boolean;
  onRefresh: () => void;
  onCreateClick: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div>
          <div className="text-xs text-muted-foreground">全部钱包合计</div>
          <div className="tabular-nums text-2xl font-bold text-emerald-600">
            {formatMoney(total, "TWD")}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">钱包数(不含分组)</div>
          <div className="tabular-nums text-2xl font-bold">{count}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isFetching}>
          <RefreshCcw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          <span className="ml-1.5">刷新</span>
        </Button>
        <Button size="sm" onClick={onCreateClick}>
          <Plus className="h-3.5 w-3.5" />
          <span className="ml-1.5">新增子钱包</span>
        </Button>
      </div>
    </div>
  );
}

// CEO 2026-05-18 v2: 覆盖式更新 - 输入"今日 0 点余额", 系统自动算与当前余额的差额, 走 credit/debit
function UpdateBalanceModal({
  wallet,
  onClose
}: {
  wallet: TaiwanWallet;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [newBalanceStr, setNewBalanceStr] = useState("");
  const [remark, setRemark] = useState("日终对账(0 点)");
  const [operatorName, setOperatorName] = useState(getStoredOperatorName());
  const [error, setError] = useState<string | null>(null);

  const currentMinor = wallet.balanceMinor;
  const currentUnits = currentMinor / 100;

  const parsed = (() => {
    const s = newBalanceStr.trim();
    if (s === "") return { valid: false, newMinor: 0, delta: 0 };
    const n = Number(s);
    if (!Number.isFinite(n) || n < 0) return { valid: false, newMinor: 0, delta: 0 };
    const newMinor = Math.round(n * 100);
    return { valid: true, newMinor, delta: newMinor - currentMinor };
  })();

  const mutation = useMutation({
    mutationFn: async () => {
      if (!parsed.valid) {
        throw new Error("请填写有效的余额(>= 0)");
      }
      if (parsed.delta === 0) {
        throw new Error("新余额和当前一致, 无需更新");
      }
      if (!operatorName.trim()) {
        throw new Error("请填写操作人");
      }
      setStoredOperatorName(operatorName.trim());
      const absDeltaUnits = Math.abs(parsed.delta) / 100;
      const payload = {
        amount: absDeltaUnits.toFixed(2),
        remark: remark.trim() === "" ? undefined : remark.trim(),
        operatorName: operatorName.trim()
      };
      if (parsed.delta > 0) {
        return creditTaiwanWallet(wallet.id, payload);
      }
      return debitTaiwanWallet(wallet.id, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-transactions", wallet.id] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "提交失败")
  });

  const deltaHint = (() => {
    if (!newBalanceStr.trim()) return null;
    if (!parsed.valid) return <span className="text-red-600">填的不是数字</span>;
    if (parsed.delta === 0) return <span className="text-muted-foreground">无变化</span>;
    const absStr = (Math.abs(parsed.delta) / 100).toFixed(2);
    return parsed.delta > 0 ? (
      <span className="text-green-600">系统将自动记入账 +TW$ {absStr}</span>
    ) : (
      <span className="text-red-600">系统将自动记出账 -TW$ {absStr}</span>
    );
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-base">更新余额 · {wallet.name}</CardTitle>
          <div className="text-xs text-muted-foreground">
            填今日 0 点的实际余额, 系统自动算差额并记入流水
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
            <div className="text-muted-foreground">当前系统余额</div>
            <div className="tabular-nums text-base font-semibold mt-0.5">
              {formatMoney(currentMinor, "TWD")}
              <span className="ml-2 text-[10px] font-normal text-muted-foreground">
                ({currentUnits.toFixed(2)})
              </span>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              今日 0 点的实际余额(TWD) — 填多少就覆盖到多少
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary tabular-nums"
              value={newBalanceStr}
              onChange={(e) => setNewBalanceStr(e.target.value)}
              placeholder="例: 12500.50"
              type="number"
              min="0"
              step="0.01"
              autoFocus
            />
            {deltaHint ? <div className="text-xs">{deltaHint}</div> : null}
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">操作人</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={operatorName}
              onChange={(e) => setOperatorName(e.target.value)}
              placeholder="比如 CEO / 黄呈煜 / 李睿旭"
            />
            <div className="text-[10px] text-muted-foreground">下次会自动填上次的名字</div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">备注</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder="默认: 日终对账(0 点)"
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
              disabled={mutation.isPending || !parsed.valid || parsed.delta === 0}
            >
              {mutation.isPending ? "提交中..." : "确认"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function EditWalletModal({
  wallet,
  onClose
}: {
  wallet: TaiwanWallet;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(wallet.name);
  const [remark, setRemark] = useState(wallet.remark ?? "");
  const [error, setError] = useState<string | null>(null);

  const updateMut = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error("钱包名不能为空");
      return updateTaiwanWallet(wallet.id, { name: name.trim(), remark: remark.trim() || null });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteTaiwanWallet(wallet.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "删除失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-base">编辑钱包 · {wallet.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">钱包名</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">
              备注(卡号 / 注册人 等)
            </div>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder={"卡号: XXX-XXXXXXXX\n注册人: 黄呈煜"}
            />
          </div>
          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-600">
              {error}
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (confirm(`确定删除钱包 "${wallet.name}"? 余额必须为 0 才能删除。`)) {
                  deleteMut.mutate();
                }
              }}
              disabled={deleteMut.isPending || updateMut.isPending}
              className="text-red-600 border-red-300 hover:bg-red-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="ml-1">删除</span>
            </Button>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={onClose} disabled={updateMut.isPending}>
                取消
              </Button>
              <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
                {updateMut.isPending ? "保存中..." : "保存"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateWalletModal({
  groups,
  onClose
}: {
  groups: TaiwanWallet[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [parentId, setParentId] = useState<string>(groups[0]?.id ?? "");
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error("钱包名不能为空");
      if (!parentId) throw new Error("请选择分组");
      return createTaiwanWallet({
        name: name.trim(),
        parentId: Number(parentId),
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "创建失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-base">新增子钱包</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">归属分组</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
            >
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">钱包名</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例: 玉山银行 / 7-11 / 中信8591"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">备注(卡号 / 注册人)</div>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder={"卡号: XXX-XXXXXXXX\n注册人: 黄呈煜"}
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
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? "创建中..." : "创建"}
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
            <CardTitle className="text-base">{wallet.name} · 流水</CardTitle>
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
                <TableHead>操作人</TableHead>
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
                      <Badge tone={isIn ? "success" : "danger"}>{isIn ? "入账" : "出账"}</Badge>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums font-semibold",
                        isIn ? "text-green-600" : "text-red-600"
                      )}
                    >
                      {isIn ? "+" : "-"}
                      {formatMoney(tx.amountMinor, "TWD")}
                    </TableCell>
                    <TableCell className="text-xs">{tx.operatorName ?? "-"}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">{tx.remark ?? "-"}</TableCell>
                    <TableCell className="text-muted-foreground text-xs tabular-nums">
                      {formatDateTime(tx.createdAt)}
                    </TableCell>
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

// CEO 2026-05-18 v2: 子钱包卡片 - 显示余额 + 卡号 + 注册人 + 操作按钮
function ChildWalletCard({
  wallet,
  onUpdate,
  onEdit,
  onShowTransactions
}: {
  wallet: TaiwanWallet;
  onUpdate: () => void;
  onEdit: () => void;
  onShowTransactions: () => void;
}) {
  // CEO: 解析 remark 里的"卡号:" 和 "注册人:" 行
  const parseRemark = () => {
    if (!wallet.remark) return { cardNo: null, registrant: null };
    const lines = wallet.remark.split(/\s{2,}|\n/).map((s) => s.trim()).filter(Boolean);
    let cardNo: string | null = null;
    let registrant: string | null = null;
    for (const line of lines) {
      const cardMatch = line.match(/^(?:卡号|账号)[:：]\s*(.+)$/);
      const regMatch = line.match(/^注册人[:：]\s*(.+)$/);
      if (cardMatch) cardNo = cardMatch[1].trim();
      if (regMatch) registrant = regMatch[1].trim();
    }
    return { cardNo, registrant };
  };
  const { cardNo, registrant } = parseRemark();

  return (
    <Card className="border border-emerald-500/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-semibold truncate">{wallet.name}</CardTitle>
          <Button
            size="sm"
            variant="ghost"
            onClick={onEdit}
            className="h-6 w-6 p-0 shrink-0"
            title="编辑钱包"
          >
            <Pencil className="h-3 w-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        <div className="tabular-nums text-2xl font-bold text-emerald-600">
          {formatMoney(wallet.balanceMinor, "TWD")}
        </div>
        <div className="space-y-0.5 text-[11px] text-muted-foreground">
          {registrant ? (
            <div>
              <span className="text-foreground/70">注册人</span> · {registrant}
            </div>
          ) : null}
          {cardNo ? (
            <div className="truncate" title={cardNo}>
              <span className="text-foreground/70">卡号</span> · <span className="font-mono">{cardNo}</span>
            </div>
          ) : null}
          {!cardNo && !registrant ? (
            <div className="italic">无附加信息(点 ✏️ 添加)</div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <Button size="sm" onClick={onUpdate} className="h-7 px-2.5">
            <ArrowDownLeft className="h-3 w-3 text-green-100" />
            <ArrowUpRight className="h-3 w-3 text-red-100 -ml-1" />
            <span className="ml-1 text-xs">更新余额</span>
          </Button>
          <Button size="sm" variant="outline" onClick={onShowTransactions} className="h-7 px-2.5">
            <ListOrdered className="h-3 w-3" />
            <span className="ml-1 text-xs">流水</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function GroupCard({
  group,
  children,
  defaultOpen,
  onUpdate,
  onEdit,
  onShowTransactions
}: {
  group: TaiwanWallet;
  children: TaiwanWallet[];
  defaultOpen: boolean;
  onUpdate: (w: TaiwanWallet) => void;
  onEdit: (w: TaiwanWallet) => void;
  onShowTransactions: (w: TaiwanWallet) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const groupTotal = children.reduce((s, c) => s + c.balanceMinor, 0);
  return (
    <Card className="border border-emerald-500/40">
      <CardHeader
        className="cursor-pointer pb-3"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <WalletIcon className="h-4 w-4 text-emerald-600" />
            <span>{group.name}</span>
            <span className="text-xs font-normal text-muted-foreground">
              ({children.length} 个钱包)
            </span>
          </CardTitle>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-[10px] text-muted-foreground">分组合计</div>
              <div className="tabular-nums text-lg font-semibold text-emerald-700">
                {formatMoney(groupTotal, "TWD")}
              </div>
            </div>
            {open ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
        </div>
      </CardHeader>
      {open ? (
        <CardContent>
          {children.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-4 text-center text-xs text-muted-foreground">
              这个分组下还没有钱包, 点顶部"新增子钱包"加一个
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {children.map((w) => (
                <ChildWalletCard
                  key={w.id}
                  wallet={w}
                  onUpdate={() => onUpdate(w)}
                  onEdit={() => onEdit(w)}
                  onShowTransactions={() => onShowTransactions(w)}
                />
              ))}
            </div>
          )}
        </CardContent>
      ) : null}
    </Card>
  );
}

export function TaiwanPage() {
  const queryClient = useQueryClient();
  const [updateTarget, setUpdateTarget] = useState<TaiwanWallet | null>(null);
  const [editTarget, setEditTarget] = useState<TaiwanWallet | null>(null);
  const [transactionsTarget, setTransactionsTarget] = useState<TaiwanWallet | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const { data: wallets = [], isFetching } = useQuery({
    queryKey: ["taiwan-wallets"],
    queryFn: getTaiwanWallets
  });

  const { data: summary } = useQuery({
    queryKey: ["taiwan-summary"],
    queryFn: getTaiwanSummary
  });

  const groups = wallets.filter((w) => w.isGroup);
  const childrenByParent = new Map<string, TaiwanWallet[]>();
  for (const w of wallets) {
    if (w.parentId) {
      const list = childrenByParent.get(w.parentId) ?? [];
      list.push(w);
      childrenByParent.set(w.parentId, list);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">台湾钱包</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          按分组管理(银行卡 / 8591 / 超商), 子钱包记录每日余额。每次更新填"今日 0 点实际余额",
          系统自动算差额并记入流水(入账/出账)。
        </p>
      </div>

      <SummaryHeader
        total={summary?.totalBalanceMinor ?? 0}
        count={summary?.walletCount ?? 0}
        isFetching={isFetching}
        onRefresh={() => {
          queryClient.invalidateQueries({ queryKey: ["taiwan-wallets"] });
          queryClient.invalidateQueries({ queryKey: ["taiwan-summary"] });
        }}
        onCreateClick={() => setShowCreate(true)}
      />

      <div className="space-y-4">
        {groups.map((group) => (
          <GroupCard
            key={group.id}
            group={group}
            children={childrenByParent.get(group.id) ?? []}
            defaultOpen
            onUpdate={setUpdateTarget}
            onEdit={setEditTarget}
            onShowTransactions={setTransactionsTarget}
          />
        ))}
        {groups.length === 0 && !isFetching ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              暂无钱包(初始化未完成, 请联系后端)
            </CardContent>
          </Card>
        ) : null}
      </div>

      {updateTarget ? (
        <UpdateBalanceModal wallet={updateTarget} onClose={() => setUpdateTarget(null)} />
      ) : null}
      {editTarget ? (
        <EditWalletModal wallet={editTarget} onClose={() => setEditTarget(null)} />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal
          wallet={transactionsTarget}
          onClose={() => setTransactionsTarget(null)}
        />
      ) : null}
      {showCreate ? (
        <CreateWalletModal groups={groups} onClose={() => setShowCreate(false)} />
      ) : null}
    </div>
  );
}
