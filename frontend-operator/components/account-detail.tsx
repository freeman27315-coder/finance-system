"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  RefreshCcw,
  Wallet,
  Zap
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CompleteOrderModal } from "@/components/complete-order-modal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import {
  getAccountDetail,
  getAccountOrders,
  syncOrders
} from "@/lib/api";
import type { StoredOperator } from "@/lib/auth";
import { formatDateTimeSeconds, stripTrailingZeros } from "@/lib/utils";
import type { OperatorOrder } from "@/types";

const SYNC_COUNTS = [10, 20, 30, 50] as const;

const MICROSOFT_LOGIN_URL = "https://login.live.com/";

export function AccountDetail({
  accountId,
  operator
}: {
  accountId: number;
  operator: StoredOperator;
}) {
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const [syncCount, setSyncCount] = useState<10 | 20 | 30 | 50>(20);
  const [completeTarget, setCompleteTarget] = useState<OperatorOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{
    ordersAdded: number;
    ordersSkipped: number;
    balance: string | null;
    failure: string | null;
  } | null>(null);

  const detailQuery = useQuery({
    queryKey: ["account-detail", accountId, operator.id],
    queryFn: () => getAccountDetail(accountId, operator.id)
  });
  const ordersQuery = useQuery({
    queryKey: ["operator-orders", accountId, operator.id],
    queryFn: () => getAccountOrders(accountId, operator.id, true)
  });

  const syncMut = useMutation({
    mutationFn: () => syncOrders(accountId, operator.id, syncCount),
    onSuccess: async (data) => {
      setError(null);
      setSyncResult({
        ordersAdded: data.ordersAdded,
        ordersSkipped: data.ordersSkipped,
        balance: data.balance?.balance ?? null,
        failure: data.failure?.message ?? null
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["account-detail", accountId] }),
        queryClient.invalidateQueries({ queryKey: ["operator-orders", accountId] })
      ]);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "同步失败")
  });

  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setError(null);
      // 简单反馈: 临时改 syncResult.failure (复用 banner)
      const old = syncResult;
      setSyncResult({
        ordersAdded: 0,
        ordersSkipped: 0,
        balance: null,
        failure: `已复制${label}到剪贴板`
      });
      setTimeout(() => setSyncResult(old), 2000);
    } catch {
      setError(`复制${label}失败，请手动选中`);
    }
  };

  if (detailQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载账号详情…
      </div>
    );
  }

  if (detailQuery.error || !detailQuery.data) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <BackButton />
        <Card>
          <CardContent className="pt-5">
            <div className="text-sm text-red-700">
              加载失败:{" "}
              {detailQuery.error instanceof Error
                ? detailQuery.error.message
                : "未知错误"}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const detail = detailQuery.data;
  const orders = ordersQuery.data ?? [];

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/95 px-6 py-3 backdrop-blur">
        <BackButton />
        <div className="text-xs text-muted-foreground">
          客服: {operator.displayName} ({operator.loginName})
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-5 px-6 py-5">
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        ) : null}
        {syncResult ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
            {syncResult.failure ?? (
              <>
                <CheckCircle2 className="mr-1 inline h-3 w-3" />
                同步完成: 新增 {syncResult.ordersAdded} 单, 跳过{" "}
                {syncResult.ordersSkipped} 单
                {syncResult.balance
                  ? `, 当前余额 ${syncResult.balance} ${detail.currency}`
                  : ""}
              </>
            )}
          </div>
        ) : null}

        {/* ----- 账号信息卡 ----- */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              {detail.accountNo ?? detail.name}
              <Badge tone={detail.country === "UK" ? "danger" : "transfer"}>
                <Globe2 className="mr-1 h-3 w-3" />
                {detail.country}
              </Badge>
              {detail.status !== "active" ? (
                <Badge tone="warning">{detail.status}</Badge>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <FieldRow
                label="登录邮箱"
                value={detail.loginEmail ?? "-"}
                copyable={detail.loginEmail ?? undefined}
                onCopy={() =>
                  detail.loginEmail && copyToClipboard(detail.loginEmail, "邮箱")
                }
              />
              <FieldRow
                label="密码"
                value={
                  detail.passwordPlain
                    ? showPassword
                      ? detail.passwordPlain
                      : "•".repeat(Math.min(12, detail.passwordPlain.length))
                    : "(未设置)"
                }
                rightSlot={
                  detail.passwordPlain ? (
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setShowPassword((s) => !s)}
                        title={showPassword ? "隐藏" : "显示"}
                      >
                        {showPassword ? (
                          <EyeOff className="h-3.5 w-3.5" />
                        ) : (
                          <Eye className="h-3.5 w-3.5" />
                        )}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          detail.passwordPlain &&
                          copyToClipboard(detail.passwordPlain, "密码")
                        }
                        title="复制"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ) : null
                }
                mono
              />
              <FieldRow
                label="账号汇率"
                value={detail.exchangeRate ? `1 ${detail.currency} = ${detail.exchangeRate} CNY` : "-"}
              />
              <FieldRow
                label="状态备注"
                value={detail.statusMessage ?? "-"}
              />
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  typeof window !== "undefined" &&
                  window.open(MICROSOFT_LOGIN_URL, "_blank")
                }
              >
                <ExternalLink className="h-3.5 w-3.5" />
                打开 Microsoft 登录页
              </Button>
              <span className="text-xs text-muted-foreground self-center">
                登录后再回来点「同步订单」
              </span>
            </div>
          </CardContent>
        </Card>

        {/* ----- 余额 + 同步 ----- */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Wallet className="h-4 w-4" />
                微软账号余额
              </CardTitle>
              <div className="mt-1 text-xs text-muted-foreground">
                上次同步: {formatDateTimeSeconds(detail.lastSyncedAt)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-semibold tabular-nums text-blue-700">
                {stripTrailingZeros(detail.localBalance)} {detail.currency}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">同步条数:</span>
              {SYNC_COUNTS.map((n) => (
                <Button
                  key={n}
                  size="sm"
                  variant={syncCount === n ? "default" : "outline"}
                  onClick={() => setSyncCount(n)}
                >
                  {n}
                </Button>
              ))}
              <div className="flex-1" />
              <Button
                onClick={() => {
                  setError(null);
                  setSyncResult(null);
                  syncMut.mutate();
                }}
                disabled={syncMut.isPending}
              >
                <Zap className="h-3.5 w-3.5" />
                {syncMut.isPending ? "同步中…" : "同步 Microsoft 订单"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ----- 待补销售订单 ----- */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>待补销售信息的订单</CardTitle>
              <div className="mt-1 text-xs text-muted-foreground">
                点订单的「补销售」补齐 → 自动转销售记录
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => ordersQuery.refetch()}
              disabled={ordersQuery.isFetching}
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              刷新
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>订单号</TableHead>
                  <TableHead className="text-right">本币金额</TableHead>
                  <TableHead>订单时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="font-mono text-xs">
                      {order.orderNo}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {stripTrailingZeros(order.amountLocal)} {order.currencyLocal}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {formatDateTimeSeconds(order.orderAt)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        onClick={() => setCompleteTarget(order)}
                      >
                        补销售
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {orders.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={4}
                      className="py-8 text-center text-xs text-muted-foreground"
                    >
                      暂无待补订单。点上方「同步 Microsoft 订单」拉新订单
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>

      {completeTarget ? (
        <CompleteOrderModal
          order={completeTarget}
          operatorId={operator.id}
          operatorDisplayName={operator.displayName}
          onClose={() => setCompleteTarget(null)}
        />
      ) : null}
    </div>
  );
}

function BackButton() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      返回工作台
    </Link>
  );
}

function FieldRow({
  label,
  value,
  rightSlot,
  copyable,
  onCopy,
  mono
}: {
  label: string;
  value: string;
  rightSlot?: React.ReactNode;
  copyable?: string;
  onCopy?: () => void;
  mono?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2">
        <span className={mono ? "font-mono text-sm flex-1 break-all" : "text-sm flex-1"}>
          {value}
        </span>
        {rightSlot ??
          (copyable ? (
            <Button size="sm" variant="ghost" onClick={onCopy} title="复制">
              <Copy className="h-3.5 w-3.5" />
            </Button>
          ) : null)}
      </div>
    </div>
  );
}
