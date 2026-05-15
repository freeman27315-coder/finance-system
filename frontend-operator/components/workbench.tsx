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
  Loader2,
  LogOut,
  PackageOpen,
  RefreshCcw,
  Undo2,
  X,
  Zap
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
import { formatDateTimeSeconds, stripTrailingZeros } from "@/lib/utils";
import type { OperatorOrder, SaleCurrency, WalletMethod } from "@/types";

// CEO 2026-05-14: 币种由"收款方式"自动锁定,客服不再手填。下拉框已移除。
// 类型 SaleCurrency 仍保留,用于 save() payload 类型标注 + 后续可能的新映射。

const MAX_CLAIMS = 3;
// CEO 2026-05-15: 这组数字原本是"同步条数"(决定每次同步从 Microsoft 抓多少单),
// 已改为"每页显示条数"(纯前端分页, 不传给后端)。
// 同步永远抓 Microsoft 过去 3 个月全部 → 后端 count 写死 200 (实际由
// _scroll_load_orders 滚到没更多自动停)。
const PAGE_SIZES = [10, 20, 30, 50] as const;
const SYNC_ALL_COUNT = 200; // 给后端的"抓所有"上限保险值
const MICROSOFT_LOGIN_URL = "https://login.live.com/";

// ===================================================================
// 主工作台 (CEO 2026-05-12 重排: 选账号 → 同步 → 历史订单 → 补销售)
// ===================================================================

export function OperatorWorkbench({ operator }: { operator: StoredOperator }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [pageSize, setPageSize] = useState<10 | 20 | 30 | 50>(20);
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
    // CEO 2026-05-15: 同步永远抓 Microsoft 过去 3 个月全部, 不再受 UI 影响
    mutationFn: () => syncOrders(selectedAccountId!, operator.id, SYNC_ALL_COUNT),
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

                {/* CEO 2026-05-15: 改为"每页显示条数", 控制下方历史订单表分页, 不传后端 */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    每页显示
                  </label>
                  <div className="flex gap-1">
                    {PAGE_SIZES.map((n) => (
                      <Button
                        key={n}
                        size="sm"
                        variant={pageSize === n ? "default" : "outline"}
                        onClick={() => setPageSize(n)}
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
                  value={`${stripTrailingZeros(claimedAccount.localBalance)} ${claimedAccount.currency}`}
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
              pageSize={pageSize}
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

// CEO 2026-05-14: 草稿模式 + 3 秒去抖自动保存
// - 客服改任一字段进入"草稿"(不立刻发请求)
// - 改完 3 秒不动 + 必填齐 → 自动 POST → 行变绿
// - 改完 3 秒不动 + 必填没齐 → 不保存, 行保持红, 草稿仍在内存
// - 关 Electron / 切账号 → 内存草稿全丢(已保存的 DB 数据保留)
type RowDraft = {
  productName?: string | null;
  salePrice?: string | null;
  saleCurrency?: SaleCurrency | null;
  walletMethodId?: number | null;
  walletItemId?: number | null;
  remark?: string | null;
};

const AUTOSAVE_COUNTDOWN_SECONDS = 3;

// CEO 2026-05-14: 必填 4 项 — 收款方式 / 备注模板 / 收款金额(>0) / 备注
// 商品名是抓取自动填的,经办人 / 币种 系统自动,均不算客服必填。
function _isRowComplete(o: {
  walletMethodId: number | null;
  walletItemId: number | null;
  salePrice: string | null;
  remark: string | null;
}): boolean {
  const priceNum = o.salePrice ? Number(o.salePrice) : 0;
  return (
    o.walletMethodId != null &&
    o.walletItemId != null &&
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    !!o.remark &&
    o.remark.trim().length > 0
  );
}

function _missingFields(o: {
  walletMethodId: number | null;
  walletItemId: number | null;
  salePrice: string | null;
  remark: string | null;
}): string[] {
  const m: string[] = [];
  if (o.walletMethodId == null) m.push("收款方式");
  if (o.walletItemId == null) m.push("备注模板");
  const priceNum = o.salePrice ? Number(o.salePrice) : 0;
  if (!(Number.isFinite(priceNum) && priceNum > 0)) m.push("收款金额");
  if (!o.remark || o.remark.trim().length === 0) m.push("备注");
  return m;
}

function HistoryOrdersTable({
  orders,
  loading,
  empty,
  operatorId,
  queryClient,
  pageSize
}: {
  orders: OperatorOrder[];
  loading: boolean;
  empty: string;
  operatorId: number;
  queryClient: ReturnType<typeof useQueryClient>;
  pageSize: number;
}) {
  // 加载钱包方式/模板用于 inline select
  const methodsQuery = useQuery({
    queryKey: ["wallet-methods"],
    queryFn: getWalletMethods
  });
  const methods: WalletMethod[] = methodsQuery.data ?? [];

  // CEO 2026-05-15: 历史订单前端分页
  const [currentPage, setCurrentPage] = useState<number>(1);
  const totalPages = Math.max(1, Math.ceil(orders.length / pageSize));

  // pageSize 变了 / 订单数变了 → 重置到第 1 页, 避免越界
  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(1);
  }, [totalPages, currentPage]);
  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize]);

  const pagedOrders = orders.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  // === 草稿状态(每行独立) ===
  const [drafts, setDrafts] = useState<Map<number, RowDraft>>(new Map());
  const [countdowns, setCountdowns] = useState<Map<number, number>>(new Map());
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const [justSavedIds, setJustSavedIds] = useState<Set<number>>(new Set());
  const timersRef = useRef<Map<number, ReturnType<typeof setInterval>>>(new Map());

  // CEO 2026-05-14 bug fix: setInterval 的回调里读 React state 会
  // 出现 stale closure (定时器启动那一刻的快照, 3 秒后还是旧的)。
  // 用 ref 持续指向最新 drafts / orders, commitDraft 通过 ref 读
  // 保证拿到最新草稿和最新 DB 数据。
  const draftsRef = useRef(drafts);
  const ordersRef = useRef(orders);
  useEffect(() => {
    draftsRef.current = drafts;
  }, [drafts]);
  useEffect(() => {
    ordersRef.current = orders;
  }, [orders]);

  // 卸载时清掉所有计时器, 防止 setInterval 泄露
  useEffect(() => {
    return () => {
      timersRef.current.forEach((t) => clearInterval(t));
      timersRef.current.clear();
    };
  }, []);

  // 把 draft 覆盖到原 order 上, 得到"当前看到的状态"
  const merge = (o: OperatorOrder): OperatorOrder => {
    const d = drafts.get(o.id);
    if (!d) return o;
    return {
      ...o,
      productName: d.productName !== undefined ? d.productName : o.productName,
      salePrice: d.salePrice !== undefined ? d.salePrice : o.salePrice,
      saleCurrency: d.saleCurrency !== undefined ? d.saleCurrency : o.saleCurrency,
      walletMethodId:
        d.walletMethodId !== undefined ? d.walletMethodId : o.walletMethodId,
      walletItemId:
        d.walletItemId !== undefined ? d.walletItemId : o.walletItemId,
      remark: d.remark !== undefined ? d.remark : o.remark
    };
  };

  // 把 null / 空字符串 / 只有空白的字符串都视为"未填", 不传给后端
  // (避免后端把 DB 中已存内容清成 null)
  const _trimOrUndef = (v: string | null | undefined): string | undefined => {
    if (v == null) return undefined;
    const t = v.trim();
    return t.length > 0 ? t : undefined;
  };

  // 真发请求保存 draft → DB
  // CEO 2026-05-14: 通过 ref 读最新 drafts/orders, 避免 setInterval
  // closure 拿到 3 秒前的旧快照, 导致看到的草稿"还差字段"提前 return。
  const commitDraft = async (orderId: number) => {
    const latestOrders = ordersRef.current;
    const latestDrafts = draftsRef.current;
    const original = latestOrders.find((o) => o.id === orderId);
    const draft = latestDrafts.get(orderId);
    if (!original || !draft) return;
    // inline merge (不能调外层 merge, 因 merge 闭包里仍是旧 drafts)
    const merged: OperatorOrder = {
      ...original,
      productName:
        draft.productName !== undefined ? draft.productName : original.productName,
      salePrice:
        draft.salePrice !== undefined ? draft.salePrice : original.salePrice,
      saleCurrency:
        draft.saleCurrency !== undefined
          ? (draft.saleCurrency as string | null)
          : original.saleCurrency,
      walletMethodId:
        draft.walletMethodId !== undefined
          ? draft.walletMethodId
          : original.walletMethodId,
      walletItemId:
        draft.walletItemId !== undefined
          ? draft.walletItemId
          : original.walletItemId,
      remark: draft.remark !== undefined ? draft.remark : original.remark
    };
    if (!_isRowComplete(merged)) return; // 必填没齐, 不存

    setSavingIds((prev) => new Set(prev).add(orderId));
    try {
      await completeOrder(orderId, {
        operatorId,
        productName: _trimOrUndef(merged.productName),
        salePrice: _trimOrUndef(merged.salePrice),
        saleCurrency: (merged.saleCurrency as SaleCurrency | null) ?? undefined,
        walletMethodId: merged.walletMethodId ?? undefined,
        walletItemId: merged.walletItemId ?? undefined,
        remark: _trimOrUndef(merged.remark)
      });
      // 清掉这一行的 draft
      setDrafts((prev) => {
        const next = new Map(prev);
        next.delete(orderId);
        return next;
      });
      // 闪 1.5s "已保存" 标识
      setJustSavedIds((prev) => new Set(prev).add(orderId));
      setTimeout(() => {
        setJustSavedIds((prev) => {
          const n = new Set(prev);
          n.delete(orderId);
          return n;
        });
      }, 1500);
      await queryClient.invalidateQueries({ queryKey: ["operator-orders"] });
    } catch (e) {
      console.error("auto-save failed", e);
    } finally {
      setSavingIds((prev) => {
        const n = new Set(prev);
        n.delete(orderId);
        return n;
      });
    }
  };

  // 启 / 重置 这一行的 3 秒倒计时
  const scheduleSave = (orderId: number) => {
    const old = timersRef.current.get(orderId);
    if (old) clearInterval(old);

    let remaining = AUTOSAVE_COUNTDOWN_SECONDS;
    setCountdowns((prev) => new Map(prev).set(orderId, remaining));

    const interval = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) {
        setCountdowns((prev) => new Map(prev).set(orderId, remaining));
      } else {
        clearInterval(interval);
        timersRef.current.delete(orderId);
        setCountdowns((prev) => {
          const n = new Map(prev);
          n.delete(orderId);
          return n;
        });
        void commitDraft(orderId);
      }
    }, 1000);

    timersRef.current.set(orderId, interval);
  };

  // 客服在某字段改了值 → 入 draft + 重置 3 秒倒计时
  const onFieldChange = (orderId: number, patch: RowDraft) => {
    setDrafts((prev) => {
      const next = new Map(prev);
      const cur = next.get(orderId) ?? {};
      next.set(orderId, { ...cur, ...patch });
      return next;
    });
    scheduleSave(orderId);
  };

  // 留作兼容: 之前 EditableCell 调用 save() 是 fire-and-forget,
  // 现在改成把改动塞进 draft, 立刻 resolve(EditableCell 仍会闪 ✓)。
  // 真正提交由 commitDraft 在 3s 倒计时结束时发起。

  return (
    <>
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">账号编号</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">订单编号</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">类型</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">同步时间</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">商品名称</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap">经办人</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[150px]">收款方式</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[150px]">备注模板</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[140px]">收款金额</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[160px]">备注</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap w-[112px] text-center">状态</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pagedOrders.map((order) => {
          const merged = merge(order);
          const selectedMethod = methods.find((m) => m.id === merged.walletMethodId);
          const itemOptions = (selectedMethod?.items ?? []).filter((it) => it.isActive);
          const lockedCurrency =
            (merged.saleCurrency as SaleCurrency | null | undefined) ??
            (selectedMethod?.currency as SaleCurrency | null | undefined) ??
            null;
          // CEO 2026-05-14: 区分 "DB 实际存了"(savedComplete) 和 "客户端看到的合并状态"(mergedComplete)
          // 行颜色只看 savedComplete (是否真存到 DB), 防止"绿色但其实是草稿"误导客服。
          const savedComplete = _isRowComplete(order);
          const mergedComplete = _isRowComplete(merged);
          const missing = _missingFields(merged);
          const countdown = countdowns.get(order.id);
          const isSaving = savingIds.has(order.id);
          const justSaved = justSavedIds.has(order.id);
          const hasDraft = drafts.has(order.id);

          // 行底色: 真存到 DB 且必填齐 → 浅绿; 其他(草稿中 / 不完整) → 浅红
          // 这样客服一眼看出"绿 = 安全, 红 = 没存"。
          const rowBg = savedComplete && !hasDraft
            ? "bg-emerald-50/50"
            : "bg-rose-50/40";

          return (
            <TableRow
              key={order.id}
              className={"align-middle transition-colors " + rowBg}
            >
              <TableCell className="px-3 py-3 font-mono text-xs whitespace-nowrap text-muted-foreground">
                {order.accountNo ?? `#${order.accountId}`}
              </TableCell>
              <TableCell className="px-3 py-3 font-mono text-xs whitespace-nowrap text-muted-foreground">
                {order.orderNo}
              </TableCell>
              <TableCell className="px-3 py-3 whitespace-nowrap">
                {/* CEO 2026-05-12: 类型暂定只有"上号", 后续给区分逻辑 */}
                <Badge tone="transfer">上号</Badge>
              </TableCell>
              <TableCell
                className="px-3 py-3 text-xs tabular-nums whitespace-nowrap text-muted-foreground"
                title={`Microsoft 订单时间: ${formatDateTimeSeconds(order.orderAt)}`}
              >
                {formatDateTimeSeconds(order.createdAt)}
              </TableCell>

              {/* 商品名 - 只读 (系统抓取, 客服不可改), 完整显示不截断 */}
              <TableCell className="px-3 py-3 text-sm whitespace-nowrap">
                {order.productName ? (
                  <span className="font-medium">{order.productName}</span>
                ) : (
                  <span
                    className="italic text-muted-foreground"
                    title="同步时未抓到商品名"
                  >
                    —
                  </span>
                )}
              </TableCell>

              {/* 经办人 - 只读, 系统自动填 */}
              <TableCell className="px-3 py-3 text-sm whitespace-nowrap">
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

              {/* 收款方式 - 选完自动锁币种 */}
              <TableCell className="px-2 py-2">
                <EditableSelectCell<number>
                  value={merged.walletMethodId}
                  options={methods
                    .filter((m) => m.isActive)
                    .map((m) => ({ value: m.id, label: m.label }))}
                  onSave={(v) => {
                    const m = v != null ? methods.find((mm) => mm.id === v) : null;
                    onFieldChange(order.id, {
                      walletMethodId: v ?? null,
                      walletItemId: null, // 换方式时清空旧 item
                      saleCurrency: (m?.currency as SaleCurrency | null) ?? null
                    });
                    return Promise.resolve();
                  }}
                />
              </TableCell>

              {/* 备注模板 */}
              <TableCell className="px-2 py-2">
                <EditableSelectCell<number>
                  value={merged.walletItemId}
                  options={itemOptions.map((it) => ({
                    value: it.id,
                    label: it.label
                  }))}
                  disabled={!selectedMethod}
                  placeholder={selectedMethod ? "请选择" : "先选收款方式"}
                  onSave={(v) => {
                    onFieldChange(order.id, { walletItemId: v ?? null });
                    return Promise.resolve();
                  }}
                />
              </TableCell>

              {/* 收款金额 + 锁定币种(币种紧贴金额后缀) */}
              <TableCell className="px-2 py-2">
                <div className="flex items-center">
                  <EditableTextCell
                    value={stripTrailingZeros(merged.salePrice)}
                    placeholder={stripTrailingZeros(order.amountLocal)}
                    inputMode="decimal"
                    onSave={(v) => {
                      onFieldChange(order.id, { salePrice: v });
                      return Promise.resolve();
                    }}
                    className="flex-1"
                  />
                  <span
                    className={
                      "ml-0.5 shrink-0 whitespace-nowrap px-1 text-xs font-semibold tracking-wide " +
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

              {/* 备注 - 必填 */}
              <TableCell className="px-2 py-2">
                <EditableTextCell
                  value={merged.remark}
                  placeholder="必填"
                  onSave={(v) => {
                    onFieldChange(order.id, { remark: v });
                    return Promise.resolve();
                  }}
                />
              </TableCell>

              {/* 状态: 倒计时 / 保存中 / 已保存 / 完整 / 缺字段 */}
              <TableCell className="px-2 py-2 text-center">
                <RowStatusBadge
                  countdown={countdown}
                  saving={isSaving}
                  justSaved={justSaved}
                  hasDraft={hasDraft}
                  isComplete={mergedComplete}
                  missing={missing}
                />
              </TableCell>
            </TableRow>
          );
        })}
        {orders.length === 0 ? (
          <TableRow>
            <TableCell colSpan={11} className="py-8 text-center text-xs text-muted-foreground">
              {loading ? "加载中…" : empty}
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
    {/* CEO 2026-05-15: 底部分页器 */}
    {orders.length > pageSize ? (
      <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs">
        <div className="text-muted-foreground">
          共 <span className="font-medium text-foreground">{orders.length}</span> 单
          ,第 <span className="font-medium text-foreground">{currentPage}</span>
          {" / "}
          <span className="font-medium text-foreground">{totalPages}</span> 页
          ,本页显示{" "}
          <span className="font-medium text-foreground">
            {pagedOrders.length}
          </span>{" "}
          条
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage(1)}
            disabled={currentPage <= 1}
            className="h-8 px-2"
          >
            首页
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="h-8 px-2"
          >
            上一页
          </Button>
          <span className="px-2 tabular-nums">
            {currentPage} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
            className="h-8 px-2"
          >
            下一页
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage(totalPages)}
            disabled={currentPage >= totalPages}
            className="h-8 px-2"
          >
            末页
          </Button>
        </div>
      </div>
    ) : null}
    </>
  );
}

// 状态徽章: 显示在每行最右侧, 反映当前行处于哪个阶段
function RowStatusBadge({
  countdown,
  saving,
  justSaved,
  hasDraft,
  isComplete,
  missing
}: {
  countdown: number | undefined;
  saving: boolean;
  justSaved: boolean;
  hasDraft: boolean;
  isComplete: boolean;
  missing: string[];
}) {
  if (saving) {
    return (
      <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-blue-100 px-2 py-1 text-[11px] font-medium text-blue-700">
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
        保存中
      </span>
    );
  }
  if (justSaved) {
    return (
      <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-emerald-100 px-2 py-1 text-[11px] font-medium text-emerald-700">
        <CheckCircle2 className="h-3 w-3 shrink-0" />
        已保存
      </span>
    );
  }
  if (countdown != null && countdown > 0) {
    // 改了字段、倒计时中
    return (
      <span
        className={
          "inline-flex h-6 min-w-[48px] items-center justify-center whitespace-nowrap rounded-md px-2 text-[11px] font-semibold tabular-nums " +
          (isComplete
            ? "bg-emerald-100 text-emerald-700"
            : "bg-amber-100 text-amber-700")
        }
        title={
          isComplete
            ? `${countdown} 秒后自动保存`
            : `${countdown} 秒…还差: ${missing.join(" / ")}`
        }
      >
        {countdown}s
      </span>
    );
  }
  if (isComplete) {
    // 完整 + 没草稿 = 已保存到 DB
    return (
      <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700">
        <CheckCircle2 className="h-3 w-3 shrink-0" />
        完成
      </span>
    );
  }
  // 不完整 (草稿停了 / 从来没碰过) → 提示缺啥
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-rose-100 px-2 py-1 text-[11px] font-medium text-rose-700"
      title={hasDraft ? `还差: ${missing.join(" / ")}` : `请补: ${missing.join(" / ")}`}
    >
      待补 {missing.length}
    </span>
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
