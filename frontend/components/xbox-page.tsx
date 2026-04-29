"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Gamepad2,
  Gift,
  ListOrdered,
  Plus,
  RefreshCcw
} from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  consumeXbox,
  createXboxAccount,
  getVendors,
  getXboxAccounts,
  getXboxSummary,
  getXboxTransactions,
  loadGiftcard,
  rechargeXbox
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Currency, XboxAccount, XboxCountry } from "@/types";

const COUNTRY_META: Record<XboxCountry, { label: string; currency: Currency; accentBorder: string; accentText: string }> = {
  US: {
    label: "美国 (USD)",
    currency: "USD",
    accentBorder: "border-blue-500/50",
    accentText: "text-blue-600"
  },
  UK: {
    label: "英国 (GBP)",
    currency: "GBP",
    accentBorder: "border-red-500/50",
    accentText: "text-red-600"
  }
};

function formatDateTime(value: string) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

function SummaryCards({ country }: { country: XboxCountry }) {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["xbox-summary"],
    queryFn: getXboxSummary
  });

  const meta = COUNTRY_META[country];
  const summary = country === "US" ? data?.us : data?.uk;
  const rmbCost = summary?.rmbCostMinor ?? 0;
  const localBalance = summary?.localBalanceMinor ?? 0;
  const accountCount = summary?.accountCount ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新汇总
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Card className={cn("border", meta.accentBorder)}>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">累计 RMB 成本</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold text-red-600">
                {formatMoney(rmbCost, "CNY")}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-red-50 text-red-600">
              <ArrowUpRight className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
        <Card className={cn("border", meta.accentBorder)}>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">本地余额</div>
              <div className={cn("mt-1 tabular-nums text-2xl font-semibold", meta.accentText)}>
                {formatMoney(localBalance, meta.currency)}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
              <ArrowDownLeft className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
        <Card className={cn("border", meta.accentBorder)}>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">账号数</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold">{accountCount}</div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
              <Gamepad2 className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CreateAccountModal({
  defaultCountry,
  onClose
}: {
  defaultCountry: XboxCountry;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [country, setCountry] = useState<XboxCountry>(defaultCountry);
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) {
        throw new Error("账号名不能为空");
      }
      return createXboxAccount({
        name: name.trim(),
        country,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-summary"] });
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
          <CardTitle>新建 XBOX 账号</CardTitle>
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
            <div className="text-sm text-muted-foreground">国家</div>
            <div className="grid grid-cols-2 rounded-md border border-border p-1">
              {(["US", "UK"] as XboxCountry[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={cn(
                    "flex h-8 items-center justify-center rounded text-sm font-medium text-muted-foreground",
                    country === item && "bg-muted text-foreground"
                  )}
                  onClick={() => setCountry(item)}
                >
                  {COUNTRY_META[item].label}
                </button>
              ))}
            </div>
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

function RechargeModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [rmbAmount, setRmbAmount] = useState("");
  const [localAmount, setLocalAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!rmbAmount || Number(rmbAmount) <= 0) {
        throw new Error("花费人民币必须大于 0");
      }
      if (!localAmount || Number(localAmount) <= 0) {
        throw new Error("到账当地货币必须大于 0");
      }
      return rechargeXbox(account.id, {
        rmbAmount,
        localAmount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-transactions", account.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "充值失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>充值 · {account.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">花费人民币</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={rmbAmount}
              onChange={(event) => setRmbAmount(event.target.value)}
              placeholder="花费人民币"
              type="number"
              min="0"
              step="0.01"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">到账当地货币（{account.currency}）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={localAmount}
              onChange={(event) => setLocalAmount(event.target.value)}
              placeholder="到账当地货币"
              type="number"
              min="0"
              step="0.01"
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
              {mutation.isPending ? "提交中..." : "确认充值"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ConsumeModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [localAmount, setLocalAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!localAmount || Number(localAmount) <= 0) {
        throw new Error("消费金额必须大于 0");
      }
      return consumeXbox(account.id, {
        localAmount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-transactions", account.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "消费失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>消费 · {account.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">消费金额（{account.currency}）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={localAmount}
              onChange={(event) => setLocalAmount(event.target.value)}
              placeholder="消费金额"
              type="number"
              min="0"
              step="0.01"
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
              {mutation.isPending ? "提交中..." : "确认消费"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function GiftcardLoadModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [vendorId, setVendorId] = useState<string>("");
  const [cardFaceAmount, setCardFaceAmount] = useState("");
  const [rmbCost, setRmbCost] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: vendors = [], isFetching: vendorsLoading } = useQuery({
    queryKey: ["vendors"],
    queryFn: getVendors
  });

  useEffect(() => {
    if (!vendorId && vendors.length > 0) {
      setVendorId(vendors[0].id);
    }
  }, [vendors, vendorId]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!vendorId) {
        throw new Error("请选择供应商");
      }
      if (!cardFaceAmount || Number(cardFaceAmount) <= 0) {
        throw new Error("卡面额必须大于 0");
      }
      if (!rmbCost || Number(rmbCost) <= 0) {
        throw new Error("RMB 成本必须大于 0");
      }
      return loadGiftcard(vendorId, {
        xboxAccountId: account.id,
        cardFaceAmount,
        rmbCost,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["xbox-accounts", account.country] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-transactions", account.id] }),
        queryClient.invalidateQueries({ queryKey: ["vendors"] }),
        queryClient.invalidateQueries({ queryKey: ["vendor-transactions", vendorId] }),
        queryClient.invalidateQueries({ queryKey: ["xbox-summary"] })
      ]);
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "礼品卡加载失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md border-purple-500/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gift className="h-5 w-5 text-purple-600" aria-hidden="true" />
            礼品卡加载 · {account.name}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">供应商</div>
            {vendorsLoading ? (
              <div className="text-sm text-muted-foreground">加载中...</div>
            ) : vendors.length === 0 ? (
              <div className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
                暂无供应商，请先到 /vendors 创建
              </div>
            ) : (
              <select
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={vendorId}
                onChange={(event) => setVendorId(event.target.value)}
              >
                {vendors.map((vendor) => (
                  <option key={vendor.id} value={vendor.id}>
                    {vendor.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">卡面额（{account.currency}）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={cardFaceAmount}
              onChange={(event) => setCardFaceAmount(event.target.value)}
              placeholder={`卡面额 ${account.currency}`}
              type="number"
              min="0"
              step="0.01"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">RMB 收购成本</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={rmbCost}
              onChange={(event) => setRmbCost(event.target.value)}
              placeholder="商定 RMB"
              type="number"
              min="0"
              step="0.01"
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
            <Button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || vendors.length === 0}
              className="bg-purple-600 text-white hover:bg-purple-700"
            >
              {mutation.isPending ? "提交中..." : "确认加载"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TransactionsModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const { data: transactions = [], isFetching } = useQuery({
    queryKey: ["xbox-transactions", account.id],
    queryFn: () => getXboxTransactions(account)
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
                <TableHead>类型</TableHead>
                <TableHead className="text-right">RMB 金额</TableHead>
                <TableHead className="text-right">本地金额</TableHead>
                <TableHead>备注</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((tx) => {
                const isRecharge = tx.type === "recharge";
                return (
                  <TableRow key={tx.id}>
                    <TableCell>
                      <Badge tone={isRecharge ? "success" : "danger"}>
                        {isRecharge ? "充值" : "消费"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {tx.rmbAmountMinor > 0 ? formatMoney(tx.rmbAmountMinor, "CNY") : "-"}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums font-semibold",
                        isRecharge ? "text-green-600" : "text-red-600"
                      )}
                    >
                      {formatMoney(tx.localAmountMinor, tx.currency)}
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

function AccountsTable({
  accounts,
  country,
  onRecharge,
  onConsume,
  onGiftcard,
  onTransactions
}: {
  accounts: XboxAccount[];
  country: XboxCountry;
  onRecharge: (account: XboxAccount) => void;
  onConsume: (account: XboxAccount) => void;
  onGiftcard: (account: XboxAccount) => void;
  onTransactions: (account: XboxAccount) => void;
}) {
  const meta = COUNTRY_META[country];
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>账号名</TableHead>
          <TableHead className="text-right">RMB 累计成本</TableHead>
          <TableHead className="text-right">本地余额</TableHead>
          <TableHead>备注</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accounts.map((account) => (
          <TableRow key={account.id}>
            <TableCell className="font-medium">{account.name}</TableCell>
            <TableCell className="text-right tabular-nums text-red-600">
              {formatMoney(account.rmbCostMinor, "CNY")}
            </TableCell>
            <TableCell className={cn("text-right tabular-nums font-semibold", meta.accentText)}>
              {formatMoney(account.localBalanceMinor, account.currency)}
            </TableCell>
            <TableCell className="text-muted-foreground">{account.remark ?? "-"}</TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => onRecharge(account)}>
                  <ArrowDownLeft className="h-4 w-4 text-green-600" aria-hidden="true" />
                  充值
                </Button>
                <Button size="sm" variant="outline" onClick={() => onConsume(account)}>
                  <ArrowUpRight className="h-4 w-4 text-red-600" aria-hidden="true" />
                  消费
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onGiftcard(account)}
                  className="border-purple-500/40 bg-purple-500/10 text-purple-700 hover:bg-purple-500/20"
                >
                  <Gift className="h-4 w-4" aria-hidden="true" />
                  礼品卡加载
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onTransactions(account)}>
                  <ListOrdered className="h-4 w-4" aria-hidden="true" />
                  流水
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
        {accounts.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
              当前 Tab 暂无账号，点击右上角「+ 新建账号」开始
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
}

export function XboxPage() {
  const [country, setCountry] = useState<XboxCountry>("US");
  const [showCreate, setShowCreate] = useState(false);
  const [rechargeTarget, setRechargeTarget] = useState<XboxAccount | null>(null);
  const [consumeTarget, setConsumeTarget] = useState<XboxAccount | null>(null);
  const [giftcardTarget, setGiftcardTarget] = useState<XboxAccount | null>(null);
  const [transactionsTarget, setTransactionsTarget] = useState<XboxAccount | null>(null);

  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-accounts", country],
    queryFn: () => getXboxAccounts(country)
  });

  const meta = COUNTRY_META[country];

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">XBOX 账号</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            按国家管理 XBOX 账号，记录 RMB 成本与本地余额，支持充值/消费/查流水。
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新账号
        </Button>
      </div>

      <div className="inline-flex rounded-md border border-border p-1">
        {(["US", "UK"] as XboxCountry[]).map((item) => (
          <button
            key={item}
            type="button"
            className={cn(
              "h-9 px-4 rounded text-sm font-medium text-muted-foreground transition-colors",
              country === item && "bg-muted text-foreground"
            )}
            onClick={() => setCountry(item)}
          >
            {COUNTRY_META[item].label}
          </button>
        ))}
      </div>

      <SummaryCards country={country} />

      <Card className={cn("border", meta.accentBorder)}>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>{meta.label} 账号列表</CardTitle>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              新建账号
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <AccountsTable
            accounts={accounts}
            country={country}
            onRecharge={setRechargeTarget}
            onConsume={setConsumeTarget}
            onGiftcard={setGiftcardTarget}
            onTransactions={setTransactionsTarget}
          />
        </CardContent>
      </Card>

      {showCreate ? (
        <CreateAccountModal defaultCountry={country} onClose={() => setShowCreate(false)} />
      ) : null}
      {rechargeTarget ? (
        <RechargeModal account={rechargeTarget} onClose={() => setRechargeTarget(null)} />
      ) : null}
      {consumeTarget ? (
        <ConsumeModal account={consumeTarget} onClose={() => setConsumeTarget(null)} />
      ) : null}
      {giftcardTarget ? (
        <GiftcardLoadModal account={giftcardTarget} onClose={() => setGiftcardTarget(null)} />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal account={transactionsTarget} onClose={() => setTransactionsTarget(null)} />
      ) : null}
    </div>
  );
}
