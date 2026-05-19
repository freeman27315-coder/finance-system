"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
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
  getMyClaimedAccounts,
  getMyClaims,
  getWalletMethods,
  getSalesWalletOptions,
  refreshAccountBalance,
  returnClaim,
  syncOrders
} from "@/lib/api";
import { clearSession, type StoredOperator } from "@/lib/auth";
import { formatDateTimeSeconds, stripTrailingZeros } from "@/lib/utils";
import type { AvailableAccount, ClaimedAccount, OperatorOrder, SaleCurrency, WalletMethod, XboxAccountDetail } from "@/types";

// CEO 2026-05-17: 国家代码 → 中文名 + 颜色 - 客服领取池卡片用
const COUNTRY_LABELS: Record<string, { label: string; accentText: string }> = {
  US: { label: "美国", accentText: "text-blue-600" },
  UK: { label: "英国", accentText: "text-red-600" },
  EU: { label: "欧元区", accentText: "text-amber-600" },
  JP: { label: "日本", accentText: "text-pink-600" },
  CN: { label: "中国", accentText: "text-emerald-600" },
  HK: { label: "香港", accentText: "text-cyan-600" },
  TW: { label: "台湾", accentText: "text-purple-600" },
  KR: { label: "韩国", accentText: "text-rose-600" },
  CA: { label: "加拿大", accentText: "text-slate-600" },
  AU: { label: "澳大利亚", accentText: "text-orange-600" },
  SG: { label: "新加坡", accentText: "text-teal-600" },
  BR: { label: "巴西", accentText: "text-green-600" },
  MX: { label: "墨西哥", accentText: "text-yellow-600" },
  NO: { label: "挪威", accentText: "text-indigo-600" },
  SE: { label: "瑞典", accentText: "text-sky-600" },
  CZ: { label: "捷克", accentText: "text-violet-600" },
  DK: { label: "丹麦", accentText: "text-lime-700" },
  HU: { label: "匈牙利", accentText: "text-stone-700" },
  PL: { label: "波兰", accentText: "text-fuchsia-600" },
  TR: { label: "土耳其", accentText: "text-orange-700" },
  CH: { label: "瑞士", accentText: "text-red-800" }
};

function getCountryLabel(code: string) {
  return COUNTRY_LABELS[code] ?? { label: code, accentText: "text-gray-600" };
}

// 状态圆点颜色
function getAvailableStatusDot(acc: AvailableAccount): { dotClass: string; tip: string } {
  if (acc.status === "disabled") return { dotClass: "bg-red-500", tip: "账号已停用" };
  if (acc.status === "error") return { dotClass: "bg-red-500", tip: acc.statusMessage || "异常" };
  if (acc.statusMessage) return { dotClass: "bg-amber-400", tip: acc.statusMessage };
  if (!acc.lastSyncedAt) return { dotClass: "bg-gray-300", tip: "尚未同步" };
  const days = (Date.now() - new Date(acc.lastSyncedAt).getTime()) / 86_400_000;
  if (days > 7) return { dotClass: "bg-amber-400", tip: `已 ${Math.floor(days)} 天未同步` };
  return {
    dotClass: "bg-emerald-500",
    tip: `状态正常 · 上次同步 ${acc.lastSyncedAt.slice(0, 16).replace("T", " ")}`
  };
}

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
  const [showPassword, setShowPassword] = useState(false);
  // CEO 2026-05-17: 顶部大类 tab - XBOX 上号同步 / 转单销售
  const [activeTab, setActiveTab] = useState<"xbox" | "transfer">("xbox");

  // 我领的账号 — 用于账号选择器
  const claimsQuery = useQuery({
    queryKey: ["operator-my-claims", operator.id],
    queryFn: () => getMyClaims(operator.id)
  });
  const activeClaims = (claimsQuery.data ?? []).filter((c) => c.isActive);

  // CEO 2026-05-17: 我领账号的全量信息(国家/余额/币种), 给下拉框 + ClaimPanel 用
  const myAccountsQuery = useQuery({
    queryKey: ["operator-my-claimed-accounts", operator.id],
    queryFn: () => getMyClaimedAccounts(operator.id)
  });
  const myAccountsMap = new Map(
    (myAccountsQuery.data ?? []).map((a) => [a.id, a])
  );

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

  // CEO 2026-05-17 卡片合一改版: 不预选, 用户主动点卡片才选中.
  // 但如果当前选中的账号已被归还/已被强制回收, 清空选中.
  useEffect(() => {
    if (
      selectedAccountId !== null &&
      activeClaims.length > 0 &&
      !activeClaims.some((c) => c.accountId === selectedAccountId)
    ) {
      setSelectedAccountId(null);
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
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claimed-accounts"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "同步失败")
  });

  // CEO 2026-05-17 卡片合一: 顶层"归还"mutation - 从合一卡片中的"归还"按钮触发
  const returnMut = useMutation({
    mutationFn: (claimId: number) => returnClaim(claimId, operator.id),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["operator-available-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claims"] });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claimed-accounts"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "归还失败")
  });

  // 客服信息
  const claimedAccount = detailQuery.data;

  // CEO 2026-05-17 任务 C: 督促补齐 - 总待补单数(所有领取账号合计) + 历史订单计数
  const totalPendingAcrossAllAccounts = (myAccountsQuery.data ?? []).reduce(
    (sum, a) => sum + (a.pendingOrderCount ?? 0),
    0
  );
  const orderStats = (() => {
    const total = orders.length;
    const pending = orders.filter((o) => o.status === "pending_complete").length;
    const converted = total - pending;
    return { total, pending, converted };
  })();

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Gamepad2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold">客服销售系统</div>
            <div className="text-xs text-muted-foreground">
              {operator.displayName} · 持有 {activeClaims.length}/{MAX_CLAIMS} 个账号
            </div>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            // CEO 2026-05-17 任务 C4: 待补订单强卡退出登录
            if (totalPendingAcrossAllAccounts > 0) {
              alert(
                `你还有 ${totalPendingAcrossAllAccounts} 单未补齐(下方"补销售")。请先补齐再退出登录。`
              );
              return;
            }
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
        {/* CEO 2026-05-17: 顶部大类 tab - XBOX 上号同步 / 转单销售 */}
        <div className="inline-flex rounded-md border border-border bg-card p-1">
          <button
            type="button"
            onClick={() => setActiveTab("xbox")}
            className={`h-9 px-4 rounded text-sm font-medium transition-colors ${
              activeTab === "xbox"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            XBOX 上号同步
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("transfer")}
            className={`h-9 px-4 rounded text-sm font-medium transition-colors ${
              activeTab === "transfer"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            转单销售
          </button>
        </div>

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

        {/* CEO 2026-05-17 任务 C1: 顶部黄条警告 - 有待补订单时常驻 */}
        {totalPendingAcrossAllAccounts > 0 ? (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 flex items-center gap-2">
            <span className="text-base">⚠️</span>
            <span>
              你有 <strong>{totalPendingAcrossAllAccounts} 单未补齐</strong>,
              归还账号 / 退出登录前请在"历史订单"里逐单点"补销售"补完。
            </span>
          </div>
        ) : null}

        {activeTab === "transfer" ? (
          /* ===== 转单销售 (待补充) ===== */
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <PackageOpen className="h-4 w-4" />
                转单销售
              </CardTitle>
              <div className="text-xs text-muted-foreground">
                CEO 后续补充具体功能, 暂时占位。
              </div>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
                此模块功能后续上线
              </div>
            </CardContent>
          </Card>
        ) : (
        <>
        {/* ----- CEO 2026-05-17 顶部双栏: 左=我领取的账号 / 右=可领账号池 ----- */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          {/* 左: 我领取的账号 (含同步/刷新/归还/每页设置) */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Zap className="h-4 w-4" />
                我领取的账号 ({activeClaims.length}/{MAX_CLAIMS})
              </CardTitle>
              <div className="text-xs text-muted-foreground">
                点账号卡片选中 → 看到完整信息 + 同步订单 / 刷新余额 / 归还 → 下方表格显示该账号订单
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {activeClaims.length === 0 ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                  <div className="font-medium">还没领取账号</div>
                  <div className="mt-1 text-xs">
                    从右侧「可领账号池」选一个领取后再来同步。
                  </div>
                </div>
              ) : (
                (myAccountsQuery.data ?? []).map((account) => (
                  <MyClaimedAccountCard
                    key={account.id}
                    account={account}
                    isSelected={selectedAccountId === account.id}
                    onSelect={() => {
                      setSelectedAccountId(account.id);
                      setSyncSummary(null);
                      setError(null);
                    }}
                    onSync={() => {
                      setError(null);
                      setSyncSummary(null);
                      syncMut.mutate();
                    }}
                    onReturn={() => returnMut.mutate(account.claimId)}
                    pageSize={pageSize}
                    onPageSizeChange={(n) => setPageSize(n as 10 | 20 | 30 | 50)}
                    detail={claimedAccount && claimedAccount.id === account.id ? claimedAccount : undefined}
                    showPassword={showPassword}
                    onTogglePassword={() => setShowPassword((s) => !s)}
                    syncPending={syncMut.isPending}
                    returnPending={returnMut.isPending}
                  />
                ))
              )}

              {syncSummary ? (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 mt-2">
                  <CheckCircle2 className="mr-1 inline h-3 w-3" />
                  {syncSummary}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/* 右: 可领账号池 - 带分页 */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <PackageOpen className="h-4 w-4" />
                可领账号池
              </CardTitle>
              <div className="text-xs text-muted-foreground">
                业务规则: 1 个账号同一时刻只能 1 人持有；每人最多 3 个
              </div>
            </CardHeader>
            <CardContent>
              <ClaimPanel operator={operator} activeClaims={activeClaims} />
            </CardContent>
          </Card>
        </div>

        {/* ----- 历史订单表 ----- */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base">
                历史订单
                {selectedAccountId !== null ? (
                  <span className="ml-3 text-xs font-normal">
                    <span className="text-muted-foreground">总计</span>
                    <span className="ml-1 tabular-nums text-foreground">{orderStats.total}</span>
                    <span className="text-muted-foreground"> · 已补齐</span>
                    <span className="ml-1 tabular-nums text-emerald-700">{orderStats.converted}</span>
                    <span className="text-muted-foreground"> · 待补</span>
                    <span className={`ml-1 tabular-nums ${orderStats.pending > 0 ? "text-red-600 font-semibold" : "text-foreground"}`}>
                      {orderStats.pending}
                    </span>
                  </span>
                ) : null}
              </CardTitle>
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
        </>
        )}
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
// CEO 2026-05-20 #134: 砍掉 walletMethodId/walletItemId, 用 walletPoolId 直选真实钱包
// CEO 2026-05-20 二次改动: 先选渠道(淘宝/台湾) → 锁币种 → 再选具体钱包
type RowDraft = {
  productName?: string | null;
  salePrice?: string | null;
  saleCurrency?: SaleCurrency | null;
  channelCode?: string | null;        // TAOBAO / TAIWAN — 草稿里临时存,真正存储是 walletPoolId
  walletPoolId?: number | null;
  walletPoolName?: string | null;
  remark?: string | null;
};

// 渠道码 → 锁定币种(CEO 2026-05-20)
const CHANNEL_TO_CURRENCY: Record<string, SaleCurrency> = {
  TAOBAO: "CNY",
  TAIWAN: "TWD"
};

const AUTOSAVE_COUNTDOWN_SECONDS = 3;

// 必填 3 项 — 收款钱包 / 收款金额(>0) / 备注
function _isRowComplete(o: {
  walletPoolId: number | null;
  salePrice: string | null;
  remark: string | null;
}): boolean {
  const priceNum = o.salePrice ? Number(o.salePrice) : 0;
  return (
    o.walletPoolId != null &&
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    !!o.remark &&
    o.remark.trim().length > 0
  );
}

function _missingFields(o: {
  walletPoolId: number | null;
  salePrice: string | null;
  remark: string | null;
}): string[] {
  const m: string[] = [];
  if (o.walletPoolId == null) m.push("收款钱包");
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
  // CEO 2026-05-20 #134: 改用真实钱包列表(7 台湾 + 3 淘宝)
  const walletsQuery = useQuery({
    queryKey: ["sales-wallet-options"],
    queryFn: getSalesWalletOptions
  });
  const walletGroups = walletsQuery.data ?? [];
  // 扁平化为单选下拉 options(暂保留 methods 不删, 防其他地方 import 报错)
  const methods: WalletMethod[] = [];

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
      walletPoolId:
        d.walletPoolId !== undefined ? d.walletPoolId : o.walletPoolId,
      walletItemLabel:
        d.walletPoolName !== undefined ? d.walletPoolName : o.walletItemLabel,
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
      walletPoolId:
        draft.walletPoolId !== undefined ? draft.walletPoolId : original.walletPoolId,
      walletItemLabel:
        draft.walletPoolName !== undefined ? draft.walletPoolName : original.walletItemLabel,
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
        walletPoolId: merged.walletPoolId ?? undefined,
        walletItemLabel: _trimOrUndef(merged.walletItemLabel),
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
      // CEO 2026-05-17: 补完销售 → 让"我的领取"账号卡的"待补单数"角标实时减
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claimed-accounts"] });
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
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[180px]">收款钱包</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[140px]">收款金额</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap min-w-[160px]">备注</TableHead>
          <TableHead className="h-12 px-3 text-xs font-medium text-muted-foreground whitespace-nowrap w-[112px] text-center">状态</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pagedOrders.map((order) => {
          const merged = merge(order);
          // CEO 2026-05-20 二次改: 先选渠道 → 锁币种 → 再选钱包
          // 行的渠道码推导: draft.channelCode 优先;否则查 walletPoolId 所在 group
          const draftRow = drafts.get(order.id);
          const channelFromDraft = draftRow?.channelCode;
          const channelFromWallet = (() => {
            const pid = merged.walletPoolId;
            if (pid == null) return null;
            for (const g of walletGroups) {
              if (g.wallets.some((w) => w.id === pid)) return g.groupCode;
            }
            return null;
          })();
          const channelCode = channelFromDraft !== undefined
            ? channelFromDraft
            : channelFromWallet;
          const channelGroup = channelCode
            ? walletGroups.find((g) => g.groupCode === channelCode)
            : null;
          // 渠道选项:固定的 2 个(淘宝/台湾),从后端 groups 里抽
          const channelOptions = walletGroups.map((g) => ({
            value: g.groupCode,
            label: `${g.groupLabel} (${CHANNEL_TO_CURRENCY[g.groupCode] ?? g.wallets[0]?.currency})`
          }));
          // 钱包选项: 选中渠道下的钱包
          const walletOptions = (channelGroup?.wallets ?? []).map((w) => ({
            value: w.id,
            label: w.name,
            name: w.name,
            currency: w.currency as SaleCurrency
          }));
          const lockedCurrency: SaleCurrency | null = channelCode
            ? CHANNEL_TO_CURRENCY[channelCode] ?? null
            : null;
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

              {/* 收款钱包 - CEO 2026-05-20: 先选渠道 → 锁币种 → 再选具体钱包 */}
              <TableCell className="px-2 py-2">
                <div className="space-y-1">
                  <EditableSelectCell<string>
                    value={channelCode ?? null}
                    options={channelOptions}
                    placeholder="选渠道"
                    onSave={(v) => {
                      const newCode = v ?? null;
                      onFieldChange(order.id, {
                        channelCode: newCode,
                        // 换渠道清空具体钱包
                        walletPoolId: null,
                        walletPoolName: null,
                        // 锁定币种
                        saleCurrency: newCode ? CHANNEL_TO_CURRENCY[newCode] ?? null : null
                      });
                      return Promise.resolve();
                    }}
                  />
                  <EditableSelectCell<number>
                    value={merged.walletPoolId}
                    options={walletOptions}
                    placeholder={channelCode ? "选钱包" : "先选渠道"}
                    disabled={!channelCode}
                    onSave={(v) => {
                      const w = v != null ? walletOptions.find((wo) => wo.value === v) : null;
                      onFieldChange(order.id, {
                        walletPoolId: v ?? null,
                        walletPoolName: w?.name ?? null
                      });
                      return Promise.resolve();
                    }}
                  />
                </div>
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
      await queryClient.invalidateQueries({ queryKey: ["operator-available-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claims"] });
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claimed-accounts"] });
    },
    onError: (err) => setPanelError(err instanceof Error ? err.message : "领取失败")
  });

  const available = availableQuery.data ?? [];
  const slotsLeft = Math.max(0, MAX_CLAIMS - activeClaims.length);

  // CEO 2026-05-17 卡片合一 + 顶部右栏: 分页(每页 4 张)
  const POOL_PAGE_SIZE = 4;
  const [poolPage, setPoolPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(available.length / POOL_PAGE_SIZE));
  const safePage = Math.min(poolPage, totalPages - 1);
  const pageStart = safePage * POOL_PAGE_SIZE;
  const pageAccounts = available.slice(pageStart, pageStart + POOL_PAGE_SIZE);

  return (
    <div className="space-y-2">
      {panelError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {panelError}
        </div>
      ) : null}

      <div className="flex items-center justify-between text-xs">
        <span>{available.length} 个可领</span>
        <span className="text-muted-foreground">还能再领 {slotsLeft} 个</span>
      </div>

      <div className="space-y-2 min-h-[200px]">
        {available.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            暂无可领账号 (CEO 后台未标"可出库")
          </div>
        ) : (
          pageAccounts.map((account) => (
            <OperatorAccountCard
              key={account.id}
              account={account}
              primaryAction={
                <Button
                  size="sm"
                  onClick={() => claimMut.mutate(account.id)}
                  disabled={claimMut.isPending || slotsLeft <= 0}
                  className="h-7 px-3"
                >
                  领取
                </Button>
              }
            />
          ))
        )}
      </div>

      {/* 分页按钮: 只有超过 1 页才显示 */}
      {totalPages > 1 ? (
        <div className="flex items-center justify-between border-t border-border pt-2 text-xs">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPoolPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="h-7 px-2"
          >
            <ChevronLeft className="h-3 w-3" />
            <span className="ml-1">上一页</span>
          </Button>
          <span className="text-muted-foreground tabular-nums">
            第 {safePage + 1} / {totalPages} 页
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPoolPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
            className="h-7 px-2"
          >
            <span className="mr-1">下一页</span>
            <ChevronRight className="h-3 w-3" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

// ===================================================================
// 小组件
// ===================================================================

// CEO 2026-05-17: 客服侧通用账号卡片 - 同时给"我的领取" + "可领账号池"用
// 显示国家中文名 + 余额 + 上次同步 + 单条刷新, 右下角按钮(领取/归还)由父组件传入
function OperatorAccountCard({
  account,
  primaryAction,
  extraTopRight
}: {
  account: AvailableAccount;
  primaryAction: React.ReactNode;
  extraTopRight?: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const countryMeta = getCountryLabel(account.country);
  const { dotClass, tip } = getAvailableStatusDot(account);
  const balance = stripTrailingZeros(account.localBalance);
  const lastSync = account.lastSyncedAt
    ? account.lastSyncedAt.slice(0, 16).replace("T", " ")
    : "尚未同步";

  const handleRefresh = async () => {
    setRefreshing(true);
    setLocalError(null);
    try {
      await refreshAccountBalance(account.id);
      await queryClient.invalidateQueries({ queryKey: ["operator-available-accounts"] });
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : "刷新失败");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="rounded-md border border-border bg-card px-3 py-2.5 space-y-1.5">
      {/* 顶部行: 圆点 + 国家中文 + 货币 + 余额 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full shrink-0 ${dotClass}`}
            title={tip}
          />
          <span className={`text-sm font-semibold ${countryMeta.accentText} shrink-0`}>
            {countryMeta.label}
          </span>
          <span className="text-[10px] text-muted-foreground shrink-0">({account.currency})</span>
        </div>
        <span className={`text-sm font-bold tabular-nums ${countryMeta.accentText} shrink-0`}>
          {balance} {account.currency}
        </span>
      </div>

      {/* 中部: 账号编号 + 邮箱 */}
      <div className="text-[11px] text-muted-foreground truncate" title={account.loginEmail ?? ""}>
        <span className="font-mono">#{account.accountNo ?? account.name}</span>
        {account.loginEmail ? <span> · {account.loginEmail}</span> : null}
      </div>

      {/* 底部行: 上次同步 + 刷新 + 领取按钮 */}
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-[10px] text-muted-foreground">上次同步: {lastSync}</span>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={handleRefresh}
            disabled={refreshing}
            title="刷新最新余额(慢, 30-60 秒)"
            className="h-7 px-2"
          >
            <RefreshCcw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            <span className="ml-1 text-xs">{refreshing ? "刷新中" : "刷新"}</span>
          </Button>
          {primaryAction}
        </div>
      </div>

      {localError ? (
        <div className="text-[10px] text-red-600">{localError}</div>
      ) : null}
    </div>
  );
}

// CEO 2026-05-17 卡片合一: 我的领取账号卡 - 紧凑/展开两态
// 展开 = 选中 (大边框 + 完整信息 + 同步按钮 + 每页设置 + 归还)
// 紧凑 = 未选 (单行 ID/国家/余额/选中/归还)
function MyClaimedAccountCard({
  account,
  isSelected,
  onSelect,
  onSync,
  onReturn,
  pageSize,
  onPageSizeChange,
  detail,
  showPassword,
  onTogglePassword,
  syncPending,
  returnPending
}: {
  account: ClaimedAccount;
  isSelected: boolean;
  onSelect: () => void;
  onSync: () => void;
  onReturn: () => void;
  pageSize: number;
  onPageSizeChange: (n: number) => void;
  detail: XboxAccountDetail | undefined;
  showPassword: boolean;
  onTogglePassword: () => void;
  syncPending: boolean;
  returnPending: boolean;
}) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const countryMeta = getCountryLabel(account.country);
  const { dotClass, tip } = getAvailableStatusDot(account);
  const balance = stripTrailingZeros(account.localBalance);
  const lastSync = account.lastSyncedAt
    ? account.lastSyncedAt.slice(0, 16).replace("T", " ")
    : "尚未同步";

  // CEO 2026-05-17: 待补订单数 - 用来禁用归还 + 显示角标
  const pendingCount = account.pendingOrderCount ?? 0;
  const cannotReturn = pendingCount > 0;
  const returnTitle = cannotReturn
    ? `还有 ${pendingCount} 单待补, 补齐后才能归还`
    : "归还此账号";

  const handleRefresh = async () => {
    setRefreshing(true);
    setLocalError(null);
    try {
      await refreshAccountBalance(account.id);
      await queryClient.invalidateQueries({ queryKey: ["operator-my-claimed-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["account-detail", account.id] });
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : "刷新失败");
    } finally {
      setRefreshing(false);
    }
  };

  const tryReturn = () => {
    if (cannotReturn) {
      alert(`还有 ${pendingCount} 单未补齐, 请先点选中卡片 → 下方表格里逐单"补销售", 全部补完才能归还此账号。`);
      return;
    }
    if (confirm(`归还账号 #${account.accountNo ?? account.id}？`)) {
      onReturn();
    }
  };

  // ---- 紧凑(未选) ----
  if (!isSelected) {
    return (
      <div
        className="rounded-md border border-border bg-card px-3 py-2 cursor-pointer hover:border-muted-foreground/50 transition-all"
        onClick={onSelect}
      >
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2.5 w-2.5 rounded-full shrink-0 ${dotClass}`} title={tip} />
          <span className={`text-sm font-semibold ${countryMeta.accentText} shrink-0`}>
            #{account.accountNo ?? account.name}
          </span>
          <span className="text-[10px] text-muted-foreground shrink-0">
            {account.country} · {account.currency}
          </span>
          {/* CEO 2026-05-17 角标: 有待补单时红色提示 */}
          {pendingCount > 0 ? (
            <span className="shrink-0 inline-flex items-center gap-0.5 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
              {pendingCount} 待补
            </span>
          ) : null}
          <span className="truncate text-[11px] text-muted-foreground flex-1 min-w-0">
            {account.loginEmail ?? "-"}
          </span>
          <span className={`text-sm font-bold tabular-nums shrink-0 ${countryMeta.accentText}`}>
            {balance} {account.currency}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              tryReturn();
            }}
            disabled={returnPending}
            title={returnTitle}
            className={`h-7 px-2 shrink-0 ${cannotReturn ? "opacity-50" : ""}`}
          >
            <Undo2 className="h-3 w-3" />
            <span className="ml-1 text-xs">归还</span>
          </Button>
        </div>
      </div>
    );
  }

  // ---- 展开(选中) ----
  return (
    <div className={`rounded-md border-2 bg-card px-4 py-3 space-y-3 shadow-sm ring-1 ring-current ${countryMeta.accentText} border-current/50`}>
      {/* 顶部: 状态/编号/国家 + 余额 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-block h-3 w-3 rounded-full shrink-0 ${dotClass}`} title={tip} />
          <span className={`text-base font-bold ${countryMeta.accentText}`}>
            #{account.accountNo ?? account.name}
          </span>
          <span className="text-xs text-muted-foreground">
            {account.country} · {account.currency}
          </span>
          <span className={`ml-1 inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium ${countryMeta.accentText}`}>
            ✓ 选中
          </span>
          {/* CEO 2026-05-17 角标: 待补单数 */}
          {pendingCount > 0 ? (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700">
              ⚠ {pendingCount} 单待补
            </span>
          ) : null}
        </div>
        <div className={`text-xl font-bold tabular-nums shrink-0 ${countryMeta.accentText}`}>
          {balance} {account.currency}
        </div>
      </div>

      {/* 中部: 邮箱 + 密码 + 同步信息 */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 text-xs">
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground">登录邮箱</div>
          <div className="flex items-center gap-1">
            <span className="truncate flex-1">{account.loginEmail ?? "-"}</span>
            {account.loginEmail ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigator.clipboard?.writeText(account.loginEmail!)}
                className="h-6 w-6 p-0 shrink-0"
                title="复制"
              >
                <Copy className="h-3 w-3" />
              </Button>
            ) : null}
          </div>
        </div>
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground">密码</div>
          <div className="flex items-center gap-1">
            <span className="font-mono flex-1 truncate text-sm">
              {detail?.passwordPlain
                ? showPassword
                  ? detail.passwordPlain
                  : "•".repeat(Math.min(10, detail.passwordPlain.length))
                : "(未设置)"}
            </span>
            {detail?.passwordPlain ? (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={onTogglePassword}
                  className="h-6 w-6 p-0"
                  title={showPassword ? "隐藏" : "显示"}
                >
                  {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => navigator.clipboard?.writeText(detail.passwordPlain!)}
                  className="h-6 w-6 p-0"
                  title="复制"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </>
            ) : null}
          </div>
        </div>
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground">上次同步</div>
          <div className="tabular-nums">{lastSync}</div>
          <a
            href={MICROSOFT_LOGIN_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            微软登录页
          </a>
        </div>
      </div>

      {/* 底部: 每页设置 + 操作按钮 */}
      <div className="flex flex-wrap items-end justify-between gap-3 border-t border-border pt-3">
        <div className="space-y-1">
          <div className="text-[10px] font-medium text-muted-foreground">每页显示订单</div>
          <div className="flex gap-1">
            {PAGE_SIZES.map((n) => (
              <Button
                key={n}
                size="sm"
                variant={pageSize === n ? "default" : "outline"}
                onClick={() => onPageSizeChange(n)}
                className="h-8 px-3"
              >
                {n}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={handleRefresh}
            disabled={refreshing}
            className="h-9 px-3"
          >
            <RefreshCcw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            <span className="ml-1.5">{refreshing ? "刷新中…" : "刷新余额"}</span>
          </Button>
          <Button size="sm" onClick={onSync} disabled={syncPending} className="h-9 px-3">
            <Zap className="h-3.5 w-3.5" />
            <span className="ml-1.5">{syncPending ? "同步中…" : "同步订单"}</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={tryReturn}
            disabled={returnPending}
            title={returnTitle}
            className={`h-9 px-3 ${cannotReturn ? "opacity-50" : ""}`}
          >
            <Undo2 className="h-3.5 w-3.5" />
            <span className="ml-1.5">归还</span>
            {pendingCount > 0 ? (
              <span className="ml-1.5 inline-flex items-center rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                {pendingCount} 待补
              </span>
            ) : null}
          </Button>
        </div>
      </div>

      {localError ? <div className="text-[11px] text-red-600">{localError}</div> : null}
    </div>
  );
}

// CEO 2026-05-17: 客服面板的账号健康状态徽章 - 绿/黄/红/灰圆点
function AccountStatusBadge({ account }: { account: XboxAccountDetail }) {
  const { dotClass, label, tip } = (() => {
    if (!account.loginEmail) {
      return {
        dotClass: "bg-gray-300",
        label: "未配置",
        tip: "账号尚未设登录邮箱/密码"
      };
    }
    if (account.status === "disabled") {
      return { dotClass: "bg-red-500", label: "已停用", tip: "账号已停用" };
    }
    if (account.status === "error") {
      return {
        dotClass: "bg-red-500",
        label: "异常",
        tip: account.statusMessage || "账号异常 (密码错 / 微软锁定)"
      };
    }
    if (account.statusMessage) {
      return {
        dotClass: "bg-amber-400",
        label: "警告",
        tip: account.statusMessage
      };
    }
    if (!account.lastSyncedAt) {
      return { dotClass: "bg-gray-300", label: "未同步", tip: "尚未同步" };
    }
    const days = (Date.now() - new Date(account.lastSyncedAt).getTime()) / 86_400_000;
    if (days > 7) {
      return {
        dotClass: "bg-amber-400",
        label: "过期",
        tip: `已 ${Math.floor(days)} 天未同步`
      };
    }
    const when = account.lastSyncedAt.slice(0, 16).replace("T", " ");
    return { dotClass: "bg-emerald-500", label: "正常", tip: `状态正常 · 上次同步 ${when}` };
  })();
  return (
    <div className="flex items-center gap-1.5" title={tip}>
      <span className={`inline-block h-2.5 w-2.5 rounded-full shrink-0 ${dotClass}`} />
      <span className="text-sm">{label}</span>
    </div>
  );
}

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
