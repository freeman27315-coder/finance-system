"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Gamepad2,
  Globe2,
  LogOut,
  PackageOpen,
  RefreshCcw,
  Undo2,
  X,
  Zap
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  EditableSelectCell,
  EditableTextCell
} from "@/components/ui/editable-cell";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import {
  claimAccount,
  completeOrder,
  getAccountDetail,
  getAccountOrders,
  getAvailableAccounts,
  getMyClaims,
  getWalletMethods,
  returnClaim,
  syncOrders
} from "@/lib/api";
import { clearSession, type StoredOperator } from "@/lib/auth";
import { formatDateTimeSeconds } from "@/lib/utils";
import type { OperatorOrder, SaleCurrency, WalletMethod } from "@/types";

// CEO 2026-05-14: 币种由"收款方式"自动锁定,客服不再手填。下拉框已移除。
// 类型 SaleCurrency 仍保留,用于 save() payload 类型标注 + 后续可能的新映射。

const MAX_CLAIMS = 3;
const SYNC_COUNTS = [10, 20, 30, 50] as const;
const MICROSOFT_LOGIN_URL = "https://login.live.com/";

// ===================================================================
// 主工作台 (CEO 2026-05-12 重排: 选账号 → 同步 → 历史订单 → 补销售)
// ===================================================================

export function OperatorWorkbench({ operator }: { operator: StoredOperator }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [syncCount, setSyncCount] = useState<10 | 20 | 30 | 50>(20);
  const [error, setError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<string | null>(null);
  const [claimPanelOpen, setClaimPanelOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // 我领的账号 — 用于账号选择器
  const claimsQuery = useQuery({
    queryKey: ["operator-my-claims", operator.id],
    queryFn: () => getMyClaims(operator.id)
  });
  const activeClaims = (claimsQuery.data ?? []).filter((c) => c.isActive);

  // 选中账号详情
  const detailQuery = useQuery({
    queryKey: ["account-detail", selectedAccountId, operator.id],
    queryFn: () => getAccountDetail(selectedAccountId!, operator.id),
    enabled: selectedAccountId !== null
  });

  // 历史订单(全部, pending + converted)
  const ordersQuery = useQuery({
    queryKey: ["operator-orders", selectedAccountId, operator.id],
    queryFn: () => getAccountOrders(selectedAccountId!, operator.id, false),
    enabled: selectedAccountId !== null
  });
  const orders = ordersQuery.data ?? [];

  // 自动选中第一个领取的账号
  useEffect(() => {
    if (selectedAccountId === null && activeClaims.length > 0) {
      setSelectedAccountId(activeClaims[0].accountId);
    }
    // 如果当前选中的账号已被归还,自动切换或清空
    if (
      selectedAccountId !== null &&
      activeClaims.length > 0 &&
      !activeClaims.some((c) => c.accountId === selectedAccountId)
    ) {
      setSelectedAccountId(activeClaims[0].accountId);
    }
    if (activeClaims.length === 0 && selectedAccountId !== null) {
      setSelectedAccountId(null);
    }
  }, [activeClaims, selectedAccountId]);

  const syncMut = useMutation({
    mutationFn: () => syncOrders(selectedAccountId!, operator.id, syncCount),
    onSuccess: async (data) => {
      setError(null);
      const balanceText = data.balance
        ? `, 余额 ${data.balance.balance} ${data.balance.currency}`
        : "";
      const failText = data.failure ? ` | 失败: ${data.failure.message}` : "";
      setSyncSummary(
        `同步完成: +${data.ordersAdded} 单 / 跳过 ${data.ordersSkipped}${balanceText}${failText}`
      );
      await queryClient.invalidateQueries({ queryKey: ["operator-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["account-detail"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "同步失败")
  });

  // 客服信息
  const claimedAccount = detailQuery.data;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Gamepad2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold">XBOX 客服销售系统</div>
            <div className="text-xs text-muted-foreground">
              {operator.displayName} · 持有 {activeClaims.length}/{MAX_CLAIMS} 个账号
            </div>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (activeClaims.length > 0) {
              if (
                !confirm(`你还持有 ${activeClaims.length} 个账号未归还，确定退出登录？`)
              ) {
                return;
              }
            }
            clearSession();
            router.replace("/login");
          }}
        >
          <LogOut className="h-3.5 w-3.5" />
          退出
        </Button>
      </header>

      <main className="mx-auto w-full max-w-7xl space-y-4 px-6 py-4">
        {error ? (
          <div className="flex items-start justify-between gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="flex-1">{error}</span>
            <button
              type="button"
              aria-label="关闭报错提示"
              onClick={() => setError(null)}
              className="shrink-0 rounded p-0.5 text-red-500 hover:bg-red-100 hover:text-red-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : null}

        {/* ----- 主操作区: 账号选择 + 同步 ----- */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Zap className="h-4 w-4" />
              选择账号 → 同步 Microsoft 订单
            </CardTitle>
            <div className="text-xs text-muted-foreground">
              主流程: 选你领的账号 → 点同步 → 下方加载历史订单 → 待补的点「补销售」
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {activeClaims.length === 0 ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                <div className="font-medium">还没领取账号</div>
                <div className="mt-1 text-xs">
                  打开下方「账号领取」面板,从「可领账号池」选一个领取后再来同步。
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto] md:items-end">
                {/* 账号选择 */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    账号 (你领取的 {activeClaims.length} 个)
                  </label>
                  <select
                    className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                    value={selectedAccountId ?? ""}
                    onChange={(e) =>
                      setSelectedAccountId(e.target.value ? Number(e.target.value) : null)
                    }
                  >
                    {activeClaims.map((claim) => (
                      <option key={claim.id} value={claim.accountId}>
                        账号 #{claim.accountId}
                        {claimedAccount && claimedAccount.id === claim.accountId
                          ? ` (${claimedAccount.accountNo ?? claimedAccount.name})`
                          : ""}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 同步条数 */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    同步条数
                  </label>
                  <div className="flex gap-1">
                    {SYNC_COUNTS.map((n) => (
                      <Button
                        key={n}
                        size="sm"
                        variant={syncCount === n ? "default" : "outline"}
                        onClick={() => setSyncCount(n)}
                        className="h-10 px-3"
                      >
                        {n}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* 同步按钮 */}
                <div className="space-y-1">
                  <label className="invisible text-xs">.</label>
                  <Button
                    className="h-10"
                    onClick={() => {
                      setError(null);
                      setSyncSummary(null);
                      syncMut.mutate();
                    }}
                    disabled={syncMut.isPending || selectedAccountId === null}
                  >
                    <Zap className="h-3.5 w-3.5" />
                    {syncMut.isPending ? "同步中…" : "同步订单"}
                  </Button>
                </div>
              </div>
            )}

            {syncSummary ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                <CheckCircle2 className="mr-1 inline h-3 w-3" />
                {syncSummary}
              </div>
            ) : null}

            {/* 当前账号信息(密码 / 邮箱 / 余额 / Microsoft 登录入口) */}
            {claimedAccount ? (
              <div className="grid grid-cols-1 gap-3 rounded-md border border-border bg-muted/30 p-3 md:grid-cols-4">
                <FieldMini label="登录邮箱" value={claimedAccount.loginEmail ?? "-"} copyable />
                <div className="space-y-1">
                  <div className="text-[10px] font-medium text-muted-foreground">密码</div>
                  <div className="flex items-center gap-1">
                    <span className="flex-1 truncate font-mono text-sm">
                      {claimedAccount.passwordPlain
                        ? showPassword
                          ? claimedAccount.passwordPlain
                          : "•".repeat(Math.min(10, claimedAccount.passwordPlain.length))
                        : "(未设置)"}
                    </span>
                    {claimedAccount.passwordPlain ? (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setShowPassword((s) => !s)}
                          className="h-6 w-6 p-0"
                          title={showPassword ? "隐藏" : "显示"}
                        >
                          {showPassword ? (
                            <EyeOff className="h-3 w-3" />
                          ) : (
                            <Eye className="h-3 w-3" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            claimedAccount.passwordPlain &&
                            navigator.clipboard?.writeText(claimedAccount.passwordPlain)
                          }
                          className="h-6 w-6 p-0"
                          title="复制"
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
                <FieldMini
                  label={`本币余额 (${claimedAccount.currency})`}
                  value={`${claimedAccount.localBalance} ${claimedAccount.currency}`}
                  mono
                />
                <div className="space-y-1">
                  <div className="text-[10px] font-medium text-muted-foreground">
                    上次同步
                  </div>
                  <div className="text-xs tabular-nums">
                    {formatDateTimeSeconds(claimedAccount.lastSyncedAt)}
                  </div>
                  <a
                    href={MICROSOFT_LOGIN_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    打开 Microsoft 登录页
                  </a>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* ----- 历史订单表 ----- */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base">历史订单</CardTitle>
              <div className="mt-1 text-xs text-muted-foreground">
                同步后所有订单(待补 + 已转销售)都列在这。点「补销售」补齐订单。
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => ordersQuery.refetch()}
              disabled={ordersQuery.isFetching || selectedAccountId === null}
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              刷新
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            <HistoryOrdersTable
              orders={orders}
              loading={selectedAccountId !== null && ordersQuery.isLoading}
              empty={
                selectedAccountId === null
                  ? "先选账号 + 点同步"
                  : "暂无订单, 点上方「同步订单」拉取"
              }
              operatorId={operator.id}
              queryClient={queryClient}
            />
          </CardContent>
        </Card>

        {/* ----- 附加: 账号领取/归还面板(默认折叠) ----- */}
        <Card>
          <CardHeader
            className="cursor-pointer pb-3"
            onClick={() => setClaimPanelOpen((v) => !v)}
          >
            <CardTitle className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <PackageOpen className="h-4 w-4" />
                账号领取 / 归还（附加功能）
              </span>
              {claimPanelOpen ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </CardTitle>
          </CardHeader>
          {claimPanelOpen ? (
            <CardContent>
              <ClaimPanel operator={operator} activeClaims={activeClaims} />
            </CardContent>
          ) : null}
        </Card>
      </main>
    </div>
  );
}

// ===================================================================
// 历史订单表 (CEO 2026-05-12: 9 列 + inline 编辑)
// - 类型: 暂统一"上号"(后续 CEO 给区分逻辑)
// - 可编辑: 商品名 / 收款金额 / 币种 / 收款方式 / 备注模板 / 备注
// - 只读: 账号编号 / 订单编号 / 类型 / 日期 / 经办人(系统自动)
// ===================================================================

function HistoryOrdersTable({
  orders,
  loading,
  empty,
  operatorId,
  queryClient
}: {
  orders: OperatorOrder[];
  loading: boolean;
  empty: string;
  operatorId: number;
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  // 加载钱包方式/模板用于 inline select
  const methodsQuery = useQuery({
    queryKey: ["wallet-methods"],
    queryFn: getWalletMethods
  });
  const methods: WalletMethod[] = methodsQuery.data ?? [];

  // 通用保存函数: 调 PATCH 后刷订单列表
  const save = async (orderId: number, payload: Record<string, unknown>) => {
    await completeOrder(orderId, {
      operatorId,
      ...(payload as {
        productName?: string;
        salePrice?: string;
        saleCurrency?: SaleCurrency;
        walletMethodId?: number;
        walletItemId?: number;
        remark?: string;
      })
    });
    await queryClient.invalidateQueries({ queryKey: ["operator-orders"] });
  };

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground">账号编号</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground">订单编号</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground">类型</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground">日期(秒)</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground w-[130px]">商品名称</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[100px]">经办人</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground min-w-[150px]">收款方式</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground min-w-[150px]">备注模板</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground min-w-[170px]">收款金额</TableHead>
          <TableHead className="h-11 px-3 text-xs font-medium text-muted-foreground min-w-[170px]">备注</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {orders.map((order) => {
          const selectedMethod = methods.find((m) => m.id === order.walletMethodId);
          const itemOptions = (selectedMethod?.items ?? []).filter((it) => it.isActive);
          // CEO 2026-05-14: 客服补销售时, 显示币种 = 已绑定方式的币种 (优先)
          // 后端若已存了 saleCurrency 走 saleCurrency, 否则 fallback method.currency。
          const lockedCurrency =
            order.saleCurrency ?? selectedMethod?.currency ?? null;
          return (
            <TableRow key={order.id} className="align-middle">
              <TableCell className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                {order.accountNo ?? `#${order.accountId}`}
              </TableCell>
              <TableCell className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                {order.orderNo}
              </TableCell>
              <TableCell className="px-3 py-2.5">
                {/* CEO 2026-05-12: 类型暂定只有"上号", 后续给区分逻辑 */}
                <Badge tone="transfer">上号</Badge>
              </TableCell>
              <TableCell className="px-3 py-2.5 text-xs tabular-nums whitespace-nowrap text-muted-foreground">
                {formatDateTimeSeconds(order.orderAt)}
              </TableCell>

              {/* 商品名 - 可编辑 */}
              <TableCell className="px-2 py-1.5">
                <EditableTextCell
                  value={order.productName}
                  placeholder="如: 5350 档"
                  onSave={(v) => save(order.id, { productName: v })}
                />
              </TableCell>

              {/* 经办人 - 只读, 系统自动填(补销售时取 operator.display_name) */}
              <TableCell className="px-3 py-2.5 text-xs whitespace-nowrap">
                {order.operatorName ? (
                  <span className="font-medium">{order.operatorName}</span>
                ) : (
                  <span
                    className="italic text-muted-foreground"
                    title="补销售时自动填写当前领取该账号的客服"
                  >
                    —
                  </span>
                )}
              </TableCell>

              {/* 收款方式 - 可编辑 select; 选定后自动锁币种 */}
              <TableCell className="px-2 py-1.5">
                <EditableSelectCell<number>
                  value={order.walletMethodId}
                  options={methods
                    .filter((m) => m.isActive)
                    .map((m) => ({ value: m.id, label: m.label }))}
                  onSave={(v) => {
                    const m = v != null ? methods.find((mm) => mm.id === v) : null;
                    return save(order.id, {
                      walletMethodId: v ?? undefined,
                      // 换方式时,清空旧 item(防止跨方式的 item 残留)
                      walletItemId: undefined,
                      // CEO 2026-05-14: 自动锁币种 = 该方式的币种
                      saleCurrency: (m?.currency as SaleCurrency | null) ?? undefined
                    });
                  }}
                />
              </TableCell>

              {/* 备注模板 - 可编辑 select, 依赖 method */}
              <TableCell className="px-2 py-1.5">
                <EditableSelectCell<number>
                  value={order.walletItemId}
                  options={itemOptions.map((it) => ({
                    value: it.id,
                    label: it.label
                  }))}
                  disabled={!selectedMethod}
                  placeholder={selectedMethod ? "请选择" : "先选收款方式"}
                  onSave={(v) => save(order.id, { walletItemId: v ?? undefined })}
                />
              </TableCell>

              {/* 收款金额 - 客服只填数字, 币种自动跟随收款方式 */}
              <TableCell className="px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <EditableTextCell
                    value={order.salePrice}
                    placeholder={order.amountLocal}
                    inputMode="decimal"
                    onSave={(v) => save(order.id, { salePrice: v })}
                    className="flex-1"
                  />
                  <span
                    className={
                      "inline-flex h-9 min-w-[56px] shrink-0 items-center justify-center " +
                      "rounded-md border border-border bg-muted/50 px-2 text-xs font-semibold tracking-wide " +
                      (lockedCurrency ? "text-foreground" : "text-muted-foreground/60")
                    }
                    title={
                      lockedCurrency
                        ? `币种由收款方式自动锁定: ${lockedCurrency}`
                        : "选好收款方式后, 币种会自动填上"
                    }
                  >
                    {lockedCurrency ?? "—"}
                  </span>
                </div>
              </TableCell>

              {/* 备注 - 可编辑 */}
              <TableCell className="px-2 py-1.5">
                <EditableTextCell
                  value={order.remark}
                  placeholder="可自由填写"
                  onSave={(v) => save(order.id, { remark: v })}
                />
              </TableCell>
            </TableRow>
          );
        })}
        {orders.length === 0 ? (
          <TableRow>
            <TableCell colSpan={10} className="py-8 text-center text-xs text-muted-foreground">
              {loading ? "加载中…" : empty}
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
}

// ===================================================================
// 附加: 账号领取/归还 (折叠面板)
// ===================================================================

function ClaimPanel({
  operator,
  activeClaims
}: {
  operator: StoredOperator;
  activeClaims: { id: number; accountId: number; claimedAt: string }[];
}) {
  const queryClient = useQueryClient();
  const [panelError, setPanelError] = useState<string | null>(null);

  const availableQuery = useQuery({
    queryKey: ["operator-available-accounts"],
    queryFn: getAvailableAccounts
  });

  const claimMut = useMutation({
    mutationFn: (accountId: number) => claimAccount(accountId, operator.id),
    onSuccess: async () => {
      setPanelError(null);
      await queryClient.invalidateQueries({
        queryKey: ["operator-available-accounts"]
      });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claims"] });
    },
    onError: (err) => setPanelError(err instanceof Error ? err.message : "领取失败")
  });

  const returnMut = useMutation({
    mutationFn: (claimId: number) => returnClaim(claimId, operator.id),
    onSuccess: async () => {
      setPanelError(null);
      await queryClient.invalidateQueries({
        queryKey: ["operator-available-accounts"]
      });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claims"] });
    },
    onError: (err) => setPanelError(err instanceof Error ? err.message : "归还失败")
  });

  const available = availableQuery.data ?? [];
  const slotsLeft = Math.max(0, MAX_CLAIMS - activeClaims.length);

  return (
    <div className="space-y-3">
      <div className="text-xs text-muted-foreground">
        业务规则: 1 个账号同一时刻只能 1 人持有；每人最多 3 个。下班前请手动归还。
      </div>

      {panelError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {panelError}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* 我领的 */}
        <div className="space-y-2">
          <div className="text-xs font-medium">
            我的领取 ({activeClaims.length}/{MAX_CLAIMS})
          </div>
          <div className="space-y-1">
            {activeClaims.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-3 py-3 text-center text-xs text-muted-foreground">
                还没领账号
              </div>
            ) : (
              activeClaims.map((claim) => (
                <div
                  key={claim.id}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2"
                >
                  <div>
                    <div className="text-sm font-medium">账号 #{claim.accountId}</div>
                    <div className="text-[10px] text-muted-foreground tabular-nums">
                      {formatDateTimeSeconds(claim.claimedAt)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (confirm(`归还账号 #${claim.accountId}？`)) {
                        returnMut.mutate(claim.id);
                      }
                    }}
                    disabled={returnMut.isPending}
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                    归还
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 可领账号池 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs font-medium">可领账号池 ({available.length})</div>
            <span className="text-[10px] text-muted-foreground">
              还能再领 {slotsLeft} 个
            </span>
          </div>
          <div className="space-y-1 max-h-[300px] overflow-y-auto">
            {available.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-3 py-3 text-center text-xs text-muted-foreground">
                暂无可领账号 (CEO 后台未标"可出库")
              </div>
            ) : (
              available.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1 text-sm font-medium">
                      <Badge tone={account.country === "UK" ? "danger" : "transfer"}>
                        <Globe2 className="mr-1 h-3 w-3" />
                        {account.country}
                      </Badge>
                      <span className="font-mono">{account.accountNo ?? account.name}</span>
                    </div>
                    <div className="truncate text-[10px] text-muted-foreground">
                      {account.loginEmail ?? "-"}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => claimMut.mutate(account.id)}
                    disabled={claimMut.isPending || slotsLeft <= 0}
                  >
                    领取
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ===================================================================
// 小组件
// ===================================================================

function FieldMini({
  label,
  value,
  copyable = false,
  mono = false
}: {
  label: string;
  value: string;
  copyable?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-medium text-muted-foreground">{label}</div>
      <div className="flex items-center gap-1">
        <span className={`${mono ? "font-mono" : ""} flex-1 truncate text-sm`}>
          {value}
        </span>
        {copyable && value !== "-" ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => navigator.clipboard?.writeText(value)}
            className="h-6 w-6 p-0"
            title="复制"
          >
            <Copy className="h-3 w-3" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}
