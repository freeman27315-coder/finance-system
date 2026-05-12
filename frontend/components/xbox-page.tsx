"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CloudDownload,
  Download,
  ExternalLink,
  Gamepad2,
  GitCompare,
  History,
  KeyRound,
  Layers,
  Link2,
  ListOrdered,
  Lock,
  Pencil,
  Plus,
  Receipt,
  RefreshCcw,
  Settings2,
  ShieldAlert,
  Trash2,
  Unlock,
  Users
} from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  changeXboxAccountPassword,
  changeXboxAccountStatus,
  consumeXbox,
  createXboxAccount,
  createXboxOrder,
  createXboxReconcileMapping,
  deleteXboxReconcileMapping,
  exportXboxSaleRecordsUrl,
  getAllClaims,
  getAssetWallets,
  getOperators,
  getXboxAccountAuditLogs,
  getXboxAccounts,
  getXboxOrderChangeLogs,
  getXboxOrders,
  getXboxReconcileMappings,
  getXboxReconcileReport,
  getXboxSaleRecordChangeLogs,
  getXboxSaleRecords,
  getXboxSalesSummary,
  getXboxSummary,
  getXboxSyncBatches,
  getXboxTransactions,
  getXboxWalletPoolOptions,
  getXboxWalletSettings,
  patchXboxAccountAvailability,
  patchXboxOrder,
  patchXboxSaleRecord,
  pushXboxWalletSettings,
  rechargeXbox,
  refreshAllXboxBalances,
  refreshXboxAccountBalance,
  returnClaim,
  triggerXboxSync,
  updateXboxAccount
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type {
  Currency,
  XboxAccount,
  XboxAccountAuditLog,
  XboxAccountStatus,
  XboxCountry,
  XboxOrder,
  XboxPoolOptionGroup,
  XboxReconcileMapping,
  XboxSaleCurrency,
  XboxSaleRecord,
  XboxWalletMethod
} from "@/types";

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

// CEO 2026-05-12: 销售日期/时间显示到秒(中国时区)
function formatDateTimeSeconds(value: string) {
  if (!value) return "-";
  return value.length >= 19 ? value.slice(0, 19).replace("T", " ") : value;
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

// 默认筛选范围: 最近 30 天 (CEO 2026-05-08 Q1:A)
function defaultDateRange(): { from: string; to: string } {
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - 30);
  return {
    from: from.toISOString().slice(0, 10),
    to: today.toISOString().slice(0, 10)
  };
}

function DateRangeFilter({
  from,
  to,
  onChange
}: {
  from: string;
  to: string;
  onChange: (next: { from: string; to: string }) => void;
}) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span>日期:</span>
      <input
        type="date"
        className="h-7 rounded border border-border bg-card px-2 text-xs"
        value={from}
        onChange={(event) => onChange({ from: event.target.value, to })}
      />
      <span>→</span>
      <input
        type="date"
        className="h-7 rounded border border-border bg-card px-2 text-xs"
        value={to}
        onChange={(event) => onChange({ from, to: event.target.value })}
      />
    </div>
  );
}

// PR P0.2++ 销售记录/订单 变更日志 Modal（CEO Q3:A）
function ChangeLogsModal({
  title,
  fetchLogs,
  onClose
}: {
  title: string;
  fetchLogs: () => Promise<{ id: string; action: string; detail: string | null; operator: string | null; createdAt: string }[]>;
  onClose: () => void;
}) {
  const { data: logs = [], isFetching } = useQuery({
    queryKey: ["xbox-change-logs", title],
    queryFn: fetchLogs
  });

  const ACTION_LABELS: Record<string, string> = {
    created: "新建",
    updated: "更新",
    completed: "补齐转销售",
    merged: "合单追加",
    wallet_pool_changed: "切换资金池"
  };

  const ACTION_TONES: Record<string, "success" | "warning" | "danger" | "neutral" | "transfer"> = {
    created: "success",
    updated: "transfer",
    completed: "success",
    merged: "warning",
    wallet_pool_changed: "danger"
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[80vh] w-full max-w-2xl flex-col">
        <CardHeader>
          <CardTitle>变更历史 · {title}</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
              {isFetching ? "加载中..." : "暂无变更记录"}
            </div>
          ) : (
            <div className="divide-y divide-border rounded-md border border-border">
              {logs.map((log) => (
                <div key={log.id} className="flex items-start gap-3 px-3 py-2">
                  <Badge tone={ACTION_TONES[log.action] ?? "neutral"}>
                    {ACTION_LABELS[log.action] ?? log.action}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">{log.detail || "(无明细)"}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {formatDateTime(log.createdAt)} · {log.operator ?? "manual"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3 flex justify-end">
            <Button variant="ghost" onClick={onClose}>关闭</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// PR P0.2++ 销售记录展开看包含订单 Modal（CEO Q4:A）
function ExpandedOrdersForSaleModal({
  saleRecord,
  onClose
}: {
  saleRecord: XboxSaleRecord;
  onClose: () => void;
}) {
  const { data: allOrders = [], isFetching } = useQuery({
    queryKey: ["xbox-orders"],
    queryFn: () => getXboxOrders()
  });
  // 过滤出本销售记录关联的订单
  const includedOrders = allOrders.filter((o) =>
    saleRecord.orderIds.includes(o.id)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[80vh] w-full max-w-3xl flex-col">
        <CardHeader>
          <CardTitle>包含订单 · 销售 #{saleRecord.id}</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            合并 {saleRecord.orderIds.length} 个订单 · 总售价{" "}
            {formatMoney(saleRecord.salePrice, saleRecord.saleCurrency as Currency)} ·
            资金池 {saleRecord.walletItemLabel}
          </div>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {includedOrders.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
              {isFetching ? "加载中..." : "未找到关联订单"}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>订单号</TableHead>
                  <TableHead className="text-right">本币金额</TableHead>
                  <TableHead className="text-right">RMB 成本</TableHead>
                  <TableHead>商品</TableHead>
                  <TableHead className="text-right">售价</TableHead>
                  <TableHead>订单时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {includedOrders.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="font-medium tabular-nums">{o.orderNo}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMoney(o.amountLocal, o.currencyLocal as Currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-red-600">
                      {formatMoney(o.rmbCost, "CNY")}
                    </TableCell>
                    <TableCell className="text-xs">{o.productName ?? "-"}</TableCell>
                    <TableCell className="text-right tabular-nums text-emerald-600">
                      {o.salePrice != null && o.saleCurrency
                        ? formatMoney(o.salePrice, o.saleCurrency as Currency)
                        : "-"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {formatDateTime(o.orderAt)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="mt-3 flex justify-end">
            <Button variant="ghost" onClick={onClose}>关闭</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


// PR P0.1 状态徽章颜色配置
const STATUS_META: Record<
  XboxAccountStatus,
  { label: string; tone: "success" | "warning" | "danger" | "neutral" }
> = {
  active: { label: "可用", tone: "success" },
  disabled: { label: "停用", tone: "neutral" },
  error: { label: "异常", tone: "danger" },
  need_verification: { label: "需验证", tone: "warning" }
};

function CreateAccountModal({
  defaultCountry: _defaultCountry,
  onClose
}: {
  defaultCountry: XboxCountry;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accountNo, setAccountNo] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [password, setPassword] = useState("");
  const [exchangeRate, setExchangeRate] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const trimmedAccountNo = accountNo.trim();
      if (!trimmedAccountNo) {
        throw new Error("账号编号不能为空");
      }
      // CEO 2026-05-12 Q1-A: 不传 country, 等首次同步根据 currency 自动识别
      return createXboxAccount({
        name: trimmedAccountNo,
        accountNo: trimmedAccountNo,
        loginEmail: loginEmail.trim() === "" ? undefined : loginEmail.trim(),
        password: password === "" ? undefined : password,
        exchangeRate: exchangeRate.trim() === "" ? undefined : exchangeRate.trim(),
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
      <Card className="w-full max-w-md max-h-[90vh] overflow-y-auto">
        <CardHeader>
          <CardTitle>新建 XBOX 账号</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            国家(US/UK)首次同步后系统自动识别，无需手动选
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">
              账号编号 <span className="text-red-600">*</span>
              <span className="ml-1 text-xs">（加卡系统对接 ID,作为账号唯一标识）</span>
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={accountNo}
              onChange={(event) => setAccountNo(event.target.value)}
              placeholder="如 BH-US-001"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">登录邮箱（选填）</div>
            <input
              type="email"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              placeholder="user@outlook.com"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">登录密码（选填,加密存储）</div>
            <input
              type="password"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="留空则不设密码"
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">汇率（选填,如 7.20）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={exchangeRate}
              onChange={(event) => setExchangeRate(event.target.value)}
              placeholder="账号固定汇率"
              inputMode="decimal"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填）</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
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

// PR P0.1 编辑账号普通字段
function EditAccountModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [accountNo, setAccountNo] = useState(account.accountNo ?? "");
  const [loginEmail, setLoginEmail] = useState(account.loginEmail ?? "");
  const [exchangeRate, setExchangeRate] = useState(
    account.exchangeRate != null ? String(account.exchangeRate) : ""
  );
  const [remark, setRemark] = useState(account.remark ?? "");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const trimmedAccountNo = accountNo.trim();
      if (!trimmedAccountNo) throw new Error("账号编号不能为空");
      return updateXboxAccount(account.id, {
        accountNo: trimmedAccountNo,
        loginEmail: loginEmail.trim(),
        exchangeRate: exchangeRate.trim() === "" ? "" : exchangeRate.trim(),
        remark: remark
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-summary"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

  // 显示头部用账号编号(若无,fallback 到老 name 字段)
  const heading = account.accountNo ?? account.name;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>编辑账号 · {heading}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">
              账号编号 <span className="text-red-600">*</span>
            </div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={accountNo}
              onChange={(event) => setAccountNo(event.target.value)}
              placeholder="如 BH-US-001"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">登录邮箱</div>
            <input
              type="email"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              placeholder="user@outlook.com"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">汇率</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={exchangeRate}
              onChange={(event) => setExchangeRate(event.target.value)}
              inputMode="decimal"
              placeholder="如 7.20"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注</div>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
            />
          </div>
          <div className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
            修改密码、状态请用对应的单独按钮（会写审计日志）
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
              {mutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// PR P0.1 修改密码（单独 Modal,写审计日志）
function ChangePasswordModal({
  account,
  onClose
}: {
  account: XboxAccount;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!password) throw new Error("密码不能为空");
      if (password !== confirm) throw new Error("两次输入的密码不一致");
      return changeXboxAccountPassword(account.id, password);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "修改失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>修改密码 · {account.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">新密码</div>
            <input
              type="password"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoFocus
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">确认密码</div>
            <input
              type="password"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
            密码会以 AES-256 加密存储,数据库里只能看到密文
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
              {mutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// PR P0.1 修改状态（单独 Modal,写审计日志）
function ChangeStatusModal({
  account,
  onClose
}: {
  account: XboxAccount;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<XboxAccountStatus>(account.status);
  const [statusMessage, setStatusMessage] = useState(account.statusMessage ?? "");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () =>
      changeXboxAccountStatus(account.id, status, statusMessage.trim() === "" ? undefined : statusMessage.trim()),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "修改失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>修改状态 · {account.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">状态</div>
            <div className="grid grid-cols-2 gap-1 rounded-md border border-border p-1">
              {(Object.keys(STATUS_META) as XboxAccountStatus[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={cn(
                    "flex h-9 items-center justify-center rounded text-sm font-medium text-muted-foreground",
                    status === s && "bg-muted text-foreground"
                  )}
                  onClick={() => setStatus(s)}
                >
                  {STATUS_META[s].label}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填,如"密码错"、"需要短信验证"）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={statusMessage}
              onChange={(event) => setStatusMessage(event.target.value)}
              placeholder="状态原因"
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
              {mutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// PR P0.1 审计日志 Modal
function AuditLogsModal({ account, onClose }: { account: XboxAccount; onClose: () => void }) {
  const { data: logs = [], isFetching } = useQuery({
    queryKey: ["xbox-audit-logs", account.id],
    queryFn: () => getXboxAccountAuditLogs(account.id)
  });

  const ACTION_LABELS: Record<XboxAccountAuditLog["action"], string> = {
    created: "新建",
    updated: "更新",
    password_changed: "改密码",
    status_changed: "改状态"
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[80vh] w-full max-w-2xl flex-col">
        <CardHeader>
          <CardTitle>审计日志 · {account.name}</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
              {isFetching ? "加载中..." : "暂无变更记录"}
            </div>
          ) : (
            <div className="divide-y divide-border rounded-md border border-border">
              {logs.map((log) => (
                <div key={log.id} className="flex items-start gap-3 px-3 py-2">
                  <Badge tone="transfer">{ACTION_LABELS[log.action] ?? log.action}</Badge>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">{log.detail || "(无明细)"}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {formatDateTime(log.createdAt)} · {log.operator ?? "manual"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-3 flex justify-end">
            <Button variant="ghost" onClick={onClose}>
              关闭
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

function StatusBadge({ status }: { status: XboxAccountStatus }) {
  const meta = STATUS_META[status];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

function AccountsTable({
  accounts,
  country,
  claimByAccountId,
  operatorById,
  onTransactions,
  onEdit,
  onChangePassword,
  onChangeStatus,
  onShowAuditLogs,
  onToggleAvailable,
  onForceRecall,
  togglePending,
  recallPending,
  onRefreshBalance,
  refreshingAccountId,
  refreshPending
}: {
  accounts: XboxAccount[];
  country: XboxCountry;
  claimByAccountId: Map<number, { id: number; operatorId: number }>;
  operatorById: Map<number, { id: number; displayName: string; loginName: string }>;
  onTransactions: (account: XboxAccount) => void;
  onEdit: (account: XboxAccount) => void;
  onChangePassword: (account: XboxAccount) => void;
  onChangeStatus: (account: XboxAccount) => void;
  onShowAuditLogs: (account: XboxAccount) => void;
  onToggleAvailable: (account: XboxAccount) => void;
  onForceRecall: (claimId: number, accountLabel: string, holderName: string) => void;
  togglePending: boolean;
  recallPending: boolean;
  onRefreshBalance: (account: XboxAccount) => void;
  refreshingAccountId: string | null;
  refreshPending: boolean;
}) {
  const meta = COUNTRY_META[country];
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>账号编号</TableHead>
          <TableHead>登录邮箱</TableHead>
          <TableHead>国家</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>领取情况</TableHead>
          <TableHead className="text-right">RMB 累计成本</TableHead>
          <TableHead className="text-right">本地余额</TableHead>
          <TableHead>备注</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accounts.map((account) => {
          const claim = claimByAccountId.get(Number(account.id));
          const holder = claim ? operatorById.get(claim.operatorId) : null;
          const isRefreshingThis = refreshPending && refreshingAccountId === account.id;
          return (
            <TableRow key={account.id}>
              <TableCell className="text-xs tabular-nums text-muted-foreground">
                {account.accountNo ?? account.name}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <span className="truncate max-w-[160px]">{account.loginEmail ?? "-"}</span>
                  {account.hasPassword ? (
                    <KeyRound className="h-3 w-3 text-emerald-600" aria-label="已设密码" />
                  ) : null}
                </div>
              </TableCell>
              <TableCell>
                {/* CEO 2026-05-12 Q1-A: 国家自动识别 */}
                {account.countryIdentified ? (
                  <Badge tone={account.country === "UK" ? "danger" : "transfer"}>
                    {account.country}
                  </Badge>
                ) : (
                  <Badge tone="neutral" title="待首次同步后系统自动识别">
                    待识别
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <StatusBadge status={account.status} />
                  {account.statusMessage ? (
                    <span className="text-[10px] text-muted-foreground truncate max-w-[120px]">
                      {account.statusMessage}
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell>
                {claim ? (
                  <div className="flex flex-col gap-0.5">
                    <Badge tone="warning">
                      <Lock className="mr-1 h-3 w-3" />
                      {holder?.displayName ?? `#${claim.operatorId}`}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">
                      {holder?.loginName ?? ""}
                    </span>
                  </div>
                ) : account.isAvailableForClaim ? (
                  <Badge tone="success">
                    <Unlock className="mr-1 h-3 w-3" />
                    可出库
                  </Badge>
                ) : (
                  <Badge tone="neutral">未上架</Badge>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums text-red-600">
                {formatMoney(account.rmbCostMinor, "CNY")}
              </TableCell>
              <TableCell className={cn("text-right tabular-nums font-semibold", meta.accentText)}>
                {/* CEO 2026-05-12 Q3-A: 余额后加币种缩写 */}
                {formatMoney(account.localBalanceMinor, account.currency)}
                <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                  {account.currency}
                </span>
              </TableCell>
              <TableCell className="text-muted-foreground text-xs">{account.remark ?? "-"}</TableCell>
              <TableCell className="text-right">
                <div className="flex flex-wrap justify-end gap-1">
                  {/* CEO 2026-05-12 Q2: 单账号刷新余额 */}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onRefreshBalance(account)}
                    disabled={refreshPending}
                    title="刷新此账号微软余额(用于判断是否出入库)"
                  >
                    <RefreshCcw
                      className={cn("h-3.5 w-3.5", isRefreshingThis && "animate-spin")}
                    />
                    {isRefreshingThis ? "刷新中" : "刷新余额"}
                  </Button>
                  <Button
                    size="sm"
                    variant={account.isAvailableForClaim ? "outline" : "default"}
                    onClick={() => onToggleAvailable(account)}
                    disabled={togglePending}
                    title={
                      account.isAvailableForClaim
                        ? "撤销可出库（客服将无法再领取此账号）"
                        : "标记为可出库，客服可领取此账号"
                    }
                  >
                    {account.isAvailableForClaim ? (
                      <>
                        <Lock className="h-3.5 w-3.5" />
                        撤销可出库
                      </>
                    ) : (
                      <>
                        <Unlock className="h-3.5 w-3.5" />
                        标可出库
                      </>
                    )}
                  </Button>
                  {claim ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        onForceRecall(
                          claim.id,
                          account.accountNo ?? account.name,
                          holder?.displayName ?? `#${claim.operatorId}`
                        )
                      }
                      disabled={recallPending}
                      title="强制回收：跳过持有人确认，CEO 直接收回账号"
                    >
                      强制回收
                    </Button>
                  ) : null}
                  <Button size="sm" variant="ghost" onClick={() => onTransactions(account)}>
                    <ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />
                    流水
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onEdit(account)}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    编辑
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onChangePassword(account)}>
                    <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                    改密码
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onChangeStatus(account)}>
                    <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                    改状态
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onShowAuditLogs(account)}>
                    <History className="h-3.5 w-3.5" aria-hidden="true" />
                    审计
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
        {accounts.length === 0 ? (
          <TableRow>
            <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
              当前 Tab 暂无账号，点击右上角「+ 新建账号」开始
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
}


// ===================================================================
// PR P0.2 - 订单 Tab
// ===================================================================

const SALE_CURRENCY_OPTIONS: XboxSaleCurrency[] = ["CNY", "USD", "USDT", "TWD"];

// Microsoft 订单同步 Modal（阶段 1: mock 数据）
function SyncOrdersModal({
  accounts,
  onClose
}: {
  accounts: XboxAccount[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [count, setCount] = useState<10 | 20 | 30 | 50>(20);
  const [result, setResult] = useState<{
    success: boolean;
    ordersAdded: number;
    ordersSkipped: number;
    balance: { currency: string; balance: string } | null;
    failure: { category: string; message: string } | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const FAILURE_LABELS: Record<string, string> = {
    password_error: "密码错误（账号锁定或改密）",
    verification_required: "需要安全验证（请人工登录建立信任设备）",
    login_page_changed: "Microsoft 登录页变化（需要更新脚本）",
    order_page_failed: "订单页访问失败",
    network_error: "网络错误",
    unknown: "未知错误"
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (!accountId) throw new Error("请选账号");
      return triggerXboxSync(accountId, count);
    },
    onSuccess: async (data) => {
      setResult({
        success: data.success,
        ordersAdded: data.ordersAdded,
        ordersSkipped: data.ordersSkipped,
        balance: data.balance,
        failure: data.failure
      });
      await queryClient.invalidateQueries({ queryKey: ["xbox-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-sync-batches"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "同步失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>同步 Microsoft 订单</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            从 Microsoft 账号自动抓取订单与余额。阶段 1 用 mock 数据,真实抓取将在阶段 2 上线。
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">所属账号</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              disabled={mutation.isPending}
            >
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.accountNo ?? acc.name} · {acc.country} · {acc.status}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">同步条数</div>
            <div className="grid grid-cols-4 gap-1 rounded-md border border-border p-1">
              {([10, 20, 30, 50] as const).map((c) => (
                <button
                  key={c}
                  type="button"
                  className={cn(
                    "h-9 rounded text-sm font-medium text-muted-foreground transition-colors",
                    count === c && "bg-muted text-foreground"
                  )}
                  onClick={() => setCount(c)}
                  disabled={mutation.isPending}
                >
                  最近 {c}
                </button>
              ))}
            </div>
          </div>

          {result ? (
            result.success ? (
              <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-800 space-y-1">
                <div className="font-medium">✓ 同步成功</div>
                <div>新增订单 {result.ordersAdded} 条 · 已存在跳过 {result.ordersSkipped} 条</div>
                {result.balance ? (
                  <div>账号余额：{result.balance.currency} {result.balance.balance}</div>
                ) : null}
              </div>
            ) : (
              <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700 space-y-1">
                <div className="font-medium">✗ 同步失败</div>
                <div>{FAILURE_LABELS[result.failure?.category ?? "unknown"] ?? result.failure?.category}</div>
                {result.failure?.message ? (
                  <div className="text-xs">{result.failure.message}</div>
                ) : null}
                <div className="text-xs mt-2 text-muted-foreground">
                  账号状态已自动置为 error,你可在「账号管理」tab 解决问题后手动改回 active。
                </div>
              </div>
            )
          ) : null}

          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              {result ? "关闭" : "取消"}
            </Button>
            {result ? null : (
              <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
                {mutation.isPending ? "同步中..." : "开始同步"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// 同步批次历史 Modal（账号维度）
function SyncBatchesModal({
  accountId,
  accountLabel,
  onClose
}: {
  accountId: string;
  accountLabel: string;
  onClose: () => void;
}) {
  const { data: batches = [], isFetching } = useQuery({
    queryKey: ["xbox-sync-batches", accountId],
    queryFn: () => getXboxSyncBatches(accountId)
  });

  const FAILURE_LABELS: Record<string, string> = {
    password_error: "密码错误",
    verification_required: "需要验证",
    login_page_changed: "登录页变化",
    order_page_failed: "订单页失败",
    network_error: "网络错误",
    unknown: "未知错误"
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[80vh] w-full max-w-3xl flex-col">
        <CardHeader>
          <CardTitle>同步历史 · {accountLabel}</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {batches.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
              {isFetching ? "加载中..." : "暂无同步记录"}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>开始时间</TableHead>
                  <TableHead>请求条数</TableHead>
                  <TableHead>抓取条数</TableHead>
                  <TableHead>结果</TableHead>
                  <TableHead>失败原因</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {batches.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="text-xs tabular-nums">{formatDateTime(b.startedAt)}</TableCell>
                    <TableCell className="text-xs tabular-nums">{b.requestedCount}</TableCell>
                    <TableCell className="text-xs tabular-nums">{b.fetchedCount}</TableCell>
                    <TableCell>
                      <Badge tone={b.success ? "success" : "danger"}>
                        {b.success ? "成功" : "失败"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {b.success
                        ? "-"
                        : `${FAILURE_LABELS[b.failureCategory ?? "unknown"] ?? b.failureCategory} ${b.failureMessage ?? ""}`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="mt-3 flex justify-end">
            <Button variant="ghost" onClick={onClose}>关闭</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateOrderModal({
  accounts,
  onClose
}: {
  accounts: XboxAccount[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [orderNo, setOrderNo] = useState("");
  const [amountLocal, setAmountLocal] = useState("");
  const [currencyLocal, setCurrencyLocal] = useState<"USD" | "GBP">("USD");
  const [orderAtDate, setOrderAtDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [orderAtTime, setOrderAtTime] = useState("12:00");
  const [exchangeRate, setExchangeRate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!accountId) throw new Error("请选账号");
      if (!orderNo.trim()) throw new Error("订单号不能为空");
      if (!amountLocal.trim()) throw new Error("本币金额不能为空");
      return createXboxOrder({
        accountId,
        orderNo: orderNo.trim(),
        amountLocal: amountLocal.trim(),
        currencyLocal,
        orderAt: `${orderAtDate}T${orderAtTime}:00`,
        exchangeRate: exchangeRate.trim() === "" ? undefined : exchangeRate.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-orders"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "创建失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md max-h-[90vh] overflow-y-auto">
        <CardHeader>
          <CardTitle>新建 XBOX 订单</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">所属账号 *</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
            >
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.accountNo ?? acc.name} · {acc.country}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">订单号 *</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={orderNo}
              onChange={(event) => setOrderNo(event.target.value)}
              placeholder="如 MS-20260508-001"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">本币金额 *</div>
              <input
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={amountLocal}
                onChange={(event) => setAmountLocal(event.target.value)}
                placeholder="100.00"
                inputMode="decimal"
              />
            </div>
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">币种 *</div>
              <div className="grid grid-cols-2 rounded-md border border-border p-1">
                {(["USD", "GBP"] as const).map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={cn(
                      "flex h-8 items-center justify-center rounded text-sm font-medium text-muted-foreground",
                      currencyLocal === c && "bg-muted text-foreground"
                    )}
                    onClick={() => setCurrencyLocal(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">订单日期 *</div>
              <input
                type="date"
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={orderAtDate}
                onChange={(event) => setOrderAtDate(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">时间</div>
              <input
                type="time"
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={orderAtTime}
                onChange={(event) => setOrderAtTime(event.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">汇率（选填,默认用账号汇率）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={exchangeRate}
              onChange={(event) => setExchangeRate(event.target.value)}
              placeholder="如 7.20"
              inputMode="decimal"
            />
          </div>
          <div className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
            RMB 成本 = 本币金额 × 汇率,创建后可在订单列表点「补齐」填业务字段
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
              {mutation.isPending ? "创建中..." : "创建订单"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CompleteOrderModal({
  order,
  accounts,
  walletMethods,
  onClose
}: {
  order: XboxOrder;
  accounts: XboxAccount[];
  walletMethods: XboxWalletMethod[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  // CEO 2026-05-12: 销售日期 = 微软订单时间(order.orderAt),系统自动填,只读
  const saleDate = order.saleDate ?? order.orderAt ?? "";
  const [productName, setProductName] = useState(order.productName ?? "");
  const [operatorName, setOperatorName] = useState(order.operatorName ?? "");
  const [salePrice, setSalePrice] = useState(
    order.salePrice != null && order.saleCurrency
      ? (order.salePrice / 100).toFixed(2)
      : ""
  );
  const [saleCurrency, setSaleCurrency] = useState<XboxSaleCurrency>(
    order.saleCurrency ?? "CNY"
  );
  const [walletMethodId, setWalletMethodId] = useState(order.walletMethodId ?? "");
  const [walletItemId, setWalletItemId] = useState(order.walletItemId ?? "");
  const [error, setError] = useState<string | null>(null);
  const [autoCountdown, setAutoCountdown] = useState<number | null>(null);

  const account = accounts.find((a) => a.id === order.accountId);
  const selectedMethod = walletMethods.find((m) => m.id === walletMethodId);
  const itemOptions = selectedMethod?.items ?? [];

  // 合单提示: 查同账号 + 同 walletItemId 的现有销售记录
  const { data: allSaleRecords = [] } = useQuery({
    queryKey: ["xbox-sale-records-all"],
    queryFn: () => getXboxSaleRecords({ accountId: order.accountId })
  });
  const existingSaleRecord = walletItemId
    ? allSaleRecords.find(
        (r) => r.accountId === order.accountId && r.walletItemId === walletItemId
      )
    : null;

  const mutation = useMutation({
    mutationFn: async () => {
      if (!productName.trim()) throw new Error("商品名不能为空");
      if (!operatorName.trim()) throw new Error("经办人不能为空");
      if (!salePrice.trim()) throw new Error("售价不能为空");
      if (!walletMethodId) throw new Error("请选收款方式");
      if (!walletItemId) throw new Error("请选备注模板");
      // saleDate 不再传 — 后端创建订单时已自动 = order_at(中国时区精确到秒)
      return patchXboxOrder(order.id, {
        productName: productName.trim(),
        operatorName: operatorName.trim(),
        salePrice: salePrice.trim(),
        saleCurrency,
        walletMethodId,
        walletItemId
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-sale-records"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-sales-summary"] });
      await queryClient.invalidateQueries({ queryKey: ["asset-wallets"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

  // CEO 2026-05-08 Q4:A - 3 秒自动保存(双保险,手动按钮也保留)
  // 仅当所有必填字段都填齐 + 还没在保存中 + 没出错才触发
  const allFieldsReady =
    productName.trim() !== "" &&
    operatorName.trim() !== "" &&
    salePrice.trim() !== "" &&
    !!walletMethodId &&
    !!walletItemId;

  useEffect(() => {
    if (!allFieldsReady || mutation.isPending) {
      setAutoCountdown(null);
      return;
    }
    let counter = 3;
    setAutoCountdown(counter);
    const tick = setInterval(() => {
      counter -= 1;
      if (counter <= 0) {
        clearInterval(tick);
        setAutoCountdown(null);
        mutation.mutate();
      } else {
        setAutoCountdown(counter);
      }
    }, 1000);
    return () => {
      clearInterval(tick);
      setAutoCountdown(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productName, operatorName, salePrice, saleCurrency, walletMethodId, walletItemId, allFieldsReady]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md max-h-[90vh] overflow-y-auto">
        <CardHeader>
          <CardTitle>补齐订单 · {order.orderNo}</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            账号：{account?.accountNo ?? account?.name ?? "-"} ·
            本币 {formatMoney(order.amountLocal, order.currencyLocal as Currency)} ·
            RMB 成本 {formatMoney(order.rmbCost, "CNY")}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">销售日期（系统自动，精确到秒）</div>
            <div className="h-10 flex items-center rounded-md border border-border bg-muted px-3 text-sm tabular-nums text-muted-foreground">
              {formatDateTimeSeconds(saleDate) || "-"}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">商品名 *</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={productName}
              onChange={(event) => setProductName(event.target.value)}
              placeholder="例：5350 档"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">经办人 *</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={operatorName}
              onChange={(event) => setOperatorName(event.target.value)}
              placeholder="经办人姓名"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">售价 *</div>
              <input
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={salePrice}
                onChange={(event) => setSalePrice(event.target.value)}
                placeholder="0 表示叠加档"
                inputMode="decimal"
              />
            </div>
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">售价币种 *</div>
              <select
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={saleCurrency}
                onChange={(event) => setSaleCurrency(event.target.value as XboxSaleCurrency)}
              >
                {SALE_CURRENCY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">收款方式 *</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletMethodId}
              onChange={(event) => {
                setWalletMethodId(event.target.value);
                setWalletItemId("");
              }}
            >
              <option value="">-- 请选 --</option>
              {walletMethods.filter((m) => m.isActive).map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注模板 *</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletItemId}
              onChange={(event) => setWalletItemId(event.target.value)}
              disabled={!selectedMethod}
            >
              <option value="">-- 请选 --</option>
              {itemOptions.filter((it) => it.isActive).map((it) => (
                <option key={it.id} value={it.id}>{it.label}</option>
              ))}
            </select>
          </div>
          {/* 合单提示（CEO 2026-05-08 业务流程优化 2B）*/}
          {existingSaleRecord && walletItemId ? (
            <div className="rounded-md bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800">
              ℹ️ 该账号 + 备注模板 已有销售记录 #{existingSaleRecord.id}（当前 {existingSaleRecord.saleCurrency}{" "}
              {(existingSaleRecord.salePrice / 100).toFixed(2)}）。本订单的 {salePrice || 0} {saleCurrency}{" "}
              将累加合并到该记录。
            </div>
          ) : walletItemId ? (
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-700">
              ✓ 该账号 + 备注模板 尚无销售记录,将新建一条销售记录。
            </div>
          ) : null}

          <div className="rounded-md bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-700">
            填齐后保存,系统自动生成销售记录 + 售价进对应资金池
            {autoCountdown != null ? (
              <span className="ml-2 font-semibold text-amber-700">
                ⏱ {autoCountdown} 秒后自动保存（修改任意字段重置倒计时）
              </span>
            ) : null}
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
              {mutation.isPending ? "保存中..." : "保存并转销售"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function OrdersTab({ onJumpToSaleRecord }: { onJumpToSaleRecord?: (saleRecordId: string) => void }) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [showSync, setShowSync] = useState(false);
  const [syncBatchesTarget, setSyncBatchesTarget] = useState<XboxAccount | null>(null);
  const [completeTarget, setCompleteTarget] = useState<XboxOrder | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "pending_complete" | "converted">("all");
  const [logsTarget, setLogsTarget] = useState<XboxOrder | null>(null);
  const [dateRange, setDateRange] = useState(defaultDateRange);

  const { data: accounts = [] } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const { data: orders = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-orders", statusFilter, dateRange.from, dateRange.to],
    queryFn: () =>
      getXboxOrders({
        status: statusFilter === "all" ? undefined : statusFilter,
        from: dateRange.from,
        to: dateRange.to
      })
  });
  const { data: walletMethods = [] } = useQuery({
    queryKey: ["xbox-wallet-settings"],
    queryFn: () => getXboxWalletSettings(true)
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-md border border-border p-1">
            {(["all", "pending_complete", "converted"] as const).map((s) => (
              <button
                key={s}
                type="button"
                className={cn(
                  "h-8 px-3 rounded text-sm font-medium text-muted-foreground transition-colors",
                  statusFilter === s && "bg-muted text-foreground"
                )}
                onClick={() => setStatusFilter(s)}
              >
                {s === "all" ? "全部" : s === "pending_complete" ? "待补齐" : "已转销售"}
              </button>
            ))}
          </div>
          <DateRangeFilter from={dateRange.from} to={dateRange.to} onChange={setDateRange} />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            刷新
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowSync(true)}>
            <CloudDownload className="h-4 w-4" />
            同步 Microsoft 订单
          </Button>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" />
            新建订单
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>订单号</TableHead>
                <TableHead>账号</TableHead>
                <TableHead className="text-right">本币金额</TableHead>
                <TableHead className="text-right">RMB 成本</TableHead>
                <TableHead>订单时间</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>商品</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => {
                const account = accounts.find((a) => a.id === order.accountId);
                return (
                  <TableRow key={order.id}>
                    <TableCell className="font-medium tabular-nums">{order.orderNo}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {account?.accountNo ?? account?.name ?? "-"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMoney(order.amountLocal, order.currencyLocal as Currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-red-600">
                      {formatMoney(order.rmbCost, "CNY")}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {formatDateTime(order.orderAt)}
                    </TableCell>
                    <TableCell>
                      <Badge tone={order.status === "converted" ? "success" : "warning"}>
                        {order.status === "converted" ? "已转销售" : "待补齐"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate max-w-[160px]">
                      {order.productName ?? "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {order.status === "pending_complete" ? (
                          <Button size="sm" variant="outline" onClick={() => setCompleteTarget(order)}>
                            <Pencil className="h-3.5 w-3.5" />
                            补齐
                          </Button>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setCompleteTarget(order)}
                              title="改备注模板触发拆单"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                              改字段
                            </Button>
                            {order.saleRecordId && onJumpToSaleRecord ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => onJumpToSaleRecord(order.saleRecordId as string)}
                                title="跳转到销售记录"
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                                销售
                              </Button>
                            ) : null}
                          </>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => setLogsTarget(order)}>
                          <History className="h-3.5 w-3.5" />
                          历史
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {orders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    暂无订单,点击右上角「+ 新建订单」开始
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {showCreate ? (
        <CreateOrderModal accounts={accounts} onClose={() => setShowCreate(false)} />
      ) : null}
      {showSync ? (
        <SyncOrdersModal accounts={accounts} onClose={() => setShowSync(false)} />
      ) : null}
      {syncBatchesTarget ? (
        <SyncBatchesModal
          accountId={syncBatchesTarget.id}
          accountLabel={syncBatchesTarget.accountNo ?? syncBatchesTarget.name}
          onClose={() => setSyncBatchesTarget(null)}
        />
      ) : null}
      {completeTarget ? (
        <CompleteOrderModal
          order={completeTarget}
          accounts={accounts}
          walletMethods={walletMethods}
          onClose={() => setCompleteTarget(null)}
        />
      ) : null}
      {logsTarget ? (
        <ChangeLogsModal
          title={`订单 ${logsTarget.orderNo}`}
          fetchLogs={() => getXboxOrderChangeLogs(logsTarget.id)}
          onClose={() => setLogsTarget(null)}
        />
      ) : null}
    </div>
  );
}


// ===================================================================
// PR P0.2 - 销售记录 Tab
// ===================================================================

function EditSaleRecordModal({
  record,
  walletMethods,
  onClose
}: {
  record: XboxSaleRecord;
  walletMethods: XboxWalletMethod[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [salePrice, setSalePrice] = useState("");  // 留空表示不改
  const [saleCurrency, setSaleCurrency] = useState<XboxSaleCurrency>(record.saleCurrency);
  const [walletMethodId, setWalletMethodId] = useState(record.walletMethodId);
  const [walletItemId, setWalletItemId] = useState(record.walletItemId);
  const [productName, setProductName] = useState(record.productName);
  const [operatorName, setOperatorName] = useState(record.operatorName);
  const [error, setError] = useState<string | null>(null);

  const selectedMethod = walletMethods.find((m) => m.id === walletMethodId);
  const itemOptions = selectedMethod?.items ?? [];
  const selectedItem = itemOptions.find((it) => it.id === walletItemId);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = {
        productName: productName.trim(),
        operatorName: operatorName.trim()
      };
      if (salePrice.trim() !== "") payload.salePrice = salePrice.trim();
      if (saleCurrency !== record.saleCurrency) payload.saleCurrency = saleCurrency;
      if (walletMethodId !== record.walletMethodId) {
        payload.walletMethodId = walletMethodId;
      }
      if (walletItemId !== record.walletItemId && selectedItem) {
        payload.walletItemId = walletItemId;
        payload.walletItemLabel = selectedItem.label;
        payload.walletPoolId = selectedItem.walletPoolId;
      }
      return patchXboxSaleRecord(record.id, payload as Parameters<typeof patchXboxSaleRecord>[1]);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-sale-records"] });
      await queryClient.invalidateQueries({ queryKey: ["asset-wallets"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md max-h-[90vh] overflow-y-auto">
        <CardHeader>
          <CardTitle>修改销售记录 #{record.id}</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            当前售价 {formatMoney(record.salePrice, record.saleCurrency as Currency)}{" "}·{" "}
            合并 {record.orderIds.length} 单
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">商品名</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={productName}
              onChange={(event) => setProductName(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">经办人</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={operatorName}
              onChange={(event) => setOperatorName(event.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">新售价（留空不改）</div>
              <input
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={salePrice}
                onChange={(event) => setSalePrice(event.target.value)}
                placeholder="留空 = 不变"
                inputMode="decimal"
              />
            </div>
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">币种</div>
              <select
                className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={saleCurrency}
                onChange={(event) => setSaleCurrency(event.target.value as XboxSaleCurrency)}
              >
                {SALE_CURRENCY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">收款方式</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletMethodId}
              onChange={(event) => {
                setWalletMethodId(event.target.value);
                setWalletItemId("");
              }}
            >
              {walletMethods.filter((m) => m.isActive).map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注模板（改后钱会从旧池移到新池）</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletItemId}
              onChange={(event) => setWalletItemId(event.target.value)}
            >
              {itemOptions.filter((it) => it.isActive).map((it) => (
                <option key={it.id} value={it.id}>{it.label}</option>
              ))}
            </select>
          </div>
          <div className="rounded-md bg-amber-50 border border-amber-200 p-2 text-xs text-amber-700">
            注意：改售价/资金池后,对应钱包余额自动调整
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
              {mutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SaleRecordsTab({ highlightId }: { highlightId?: string | null }) {
  const [editTarget, setEditTarget] = useState<XboxSaleRecord | null>(null);
  const [expandTarget, setExpandTarget] = useState<XboxSaleRecord | null>(null);
  const [logsTarget, setLogsTarget] = useState<XboxSaleRecord | null>(null);
  const [dateRange, setDateRange] = useState(defaultDateRange);

  const { data: records = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-sale-records", dateRange.from, dateRange.to],
    queryFn: () => getXboxSaleRecords({ from: dateRange.from, to: dateRange.to })
  });
  const { data: summary } = useQuery({
    queryKey: ["xbox-sales-summary", dateRange.from, dateRange.to],
    queryFn: () => getXboxSalesSummary({ from: dateRange.from, to: dateRange.to })
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const { data: walletMethods = [] } = useQuery({
    queryKey: ["xbox-wallet-settings"],
    queryFn: () => getXboxWalletSettings(true)
  });

  const exportUrl = exportXboxSaleRecordsUrl({ from: dateRange.from, to: dateRange.to });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <DateRangeFilter from={dateRange.from} to={dateRange.to} onChange={setDateRange} />
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href={exportUrl} download>
              <Download className="h-4 w-4" />
              导出 Excel
            </a>
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {/* 汇总卡 (CEO 2026-05-08 Q2:A) */}
      {summary ? (
        <div className="grid gap-3 md:grid-cols-3">
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">销售记录数</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold">{summary.saleRecordCount}</div>
              <div className="mt-1 text-xs text-muted-foreground">关联订单 {summary.orderCount}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">按币种总额</div>
              <div className="mt-1 space-y-0.5">
                {summary.totalByCurrency.length === 0 ? (
                  <div className="tabular-nums text-2xl font-semibold text-muted-foreground">¥0</div>
                ) : (
                  summary.totalByCurrency.map((c) => (
                    <div key={c.currency} className="tabular-nums text-base font-semibold text-emerald-600">
                      {c.currency} {Number(c.total).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      <span className="ml-2 text-xs text-muted-foreground">({c.count} 笔)</span>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">按渠道占比（备注模板）</div>
              <div className="mt-1 space-y-0.5 max-h-24 overflow-y-auto">
                {summary.totalByItem.length === 0 ? (
                  <div className="text-sm text-muted-foreground">暂无</div>
                ) : (
                  summary.totalByItem.slice(0, 6).map((it) => (
                    <div key={`${it.itemLabel}-${it.currency}`} className="flex justify-between text-xs">
                      <span className="text-muted-foreground truncate">{it.itemLabel}</span>
                      <span className="tabular-nums font-medium">
                        {it.currency} {Number(it.total).toLocaleString("zh-CN")}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>日期</TableHead>
                <TableHead>账号</TableHead>
                <TableHead>商品</TableHead>
                <TableHead>经办人</TableHead>
                <TableHead className="text-right">售价</TableHead>
                <TableHead>资金池</TableHead>
                <TableHead className="text-right">含订单</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((record) => {
                const account = accounts.find((a) => a.id === record.accountId);
                const isHighlighted = highlightId === record.id;
                return (
                  <TableRow key={record.id} className={cn(isHighlighted && "bg-emerald-50")}>
                    <TableCell className="text-xs tabular-nums">{formatDateTimeSeconds(record.saleDate)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {account?.accountNo ?? account?.name ?? "-"}
                    </TableCell>
                    <TableCell className="truncate max-w-[200px]">{record.productName}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{record.operatorName}</TableCell>
                    <TableCell className="text-right tabular-nums font-semibold text-emerald-600">
                      {formatMoney(record.salePrice, record.saleCurrency as Currency)}
                    </TableCell>
                    <TableCell className="text-xs">{record.walletItemLabel}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 hover:text-foreground"
                        onClick={() => setExpandTarget(record)}
                        title="查看包含订单"
                      >
                        <ChevronRight className="h-3 w-3" />
                        {record.orderIds.length}
                      </button>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setExpandTarget(record)}>
                          <ChevronDown className="h-3.5 w-3.5" />
                          订单明细
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditTarget(record)}>
                          <Pencil className="h-3.5 w-3.5" />
                          修改
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setLogsTarget(record)}>
                          <History className="h-3.5 w-3.5" />
                          历史
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {records.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    暂无销售记录。在订单 Tab 补齐订单后,会自动生成销售记录。
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {editTarget ? (
        <EditSaleRecordModal
          record={editTarget}
          walletMethods={walletMethods}
          onClose={() => setEditTarget(null)}
        />
      ) : null}
      {expandTarget ? (
        <ExpandedOrdersForSaleModal
          saleRecord={expandTarget}
          onClose={() => setExpandTarget(null)}
        />
      ) : null}
      {logsTarget ? (
        <ChangeLogsModal
          title={`销售 #${logsTarget.id} ${logsTarget.productName}`}
          fetchLogs={() => getXboxSaleRecordChangeLogs(logsTarget.id)}
          onClose={() => setLogsTarget(null)}
        />
      ) : null}
    </div>
  );
}


// ===================================================================
// PR P0.2 - 钱包设置 Tab
// ===================================================================

// 把所有分组里的钱包扁平索引,方便按 id 找
function buildPoolWalletIndex(
  groups: XboxPoolOptionGroup[]
): Map<string, { name: string; currency: string; fullPath: string; groupLabel: string }> {
  const idx = new Map<string, { name: string; currency: string; fullPath: string; groupLabel: string }>();
  for (const g of groups) {
    for (const w of g.wallets) {
      idx.set(w.id, {
        name: w.name,
        currency: w.currency,
        fullPath: w.fullPath,
        groupLabel: g.groupLabel
      });
    }
  }
  return idx;
}

type DraftItem = { id?: string; code: string; label: string; walletPoolId: string; isActive: boolean };
type DraftMethod = { id?: string; code: string; label: string; isActive: boolean; items: DraftItem[] };

function WalletSettingsEditModal({
  initial,
  poolGroups,
  onClose
}: {
  initial: XboxWalletMethod[];
  poolGroups: XboxPoolOptionGroup[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [methods, setMethods] = useState<DraftMethod[]>(() =>
    initial.map((m) => ({
      id: m.id,
      code: m.code,
      label: m.label,
      isActive: m.isActive,
      items: m.items.map((it) => ({
        id: it.id,
        code: it.code,
        label: it.label,
        walletPoolId: it.walletPoolId,
        isActive: it.isActive
      }))
    }))
  );
  const [error, setError] = useState<string | null>(null);

  const addMethod = () =>
    setMethods((prev) => [
      ...prev,
      { code: "", label: "", isActive: true, items: [] }
    ]);
  const removeMethod = (i: number) =>
    setMethods((prev) => prev.filter((_, idx) => idx !== i));
  const updateMethod = (i: number, field: keyof DraftMethod, value: string | boolean) =>
    setMethods((prev) =>
      prev.map((m, idx) => (idx === i ? { ...m, [field]: value } : m))
    );
  const addItem = (mIdx: number) =>
    setMethods((prev) =>
      prev.map((m, idx) =>
        idx === mIdx
          ? {
              ...m,
              items: [...m.items, { code: "", label: "", walletPoolId: "", isActive: true }]
            }
          : m
      )
    );
  const removeItem = (mIdx: number, iIdx: number) =>
    setMethods((prev) =>
      prev.map((m, idx) =>
        idx === mIdx ? { ...m, items: m.items.filter((_, j) => j !== iIdx) } : m
      )
    );
  const updateItem = (mIdx: number, iIdx: number, field: keyof DraftItem, value: string | boolean) =>
    setMethods((prev) =>
      prev.map((m, idx) =>
        idx === mIdx
          ? {
              ...m,
              items: m.items.map((it, j) => (j === iIdx ? { ...it, [field]: value } : it))
            }
          : m
      )
    );

  const mutation = useMutation({
    mutationFn: async () => {
      // 校验
      for (const m of methods) {
        if (!m.code.trim()) throw new Error("收款方式 code 不能为空");
        if (!m.label.trim()) throw new Error("收款方式 label 不能为空");
        for (const it of m.items) {
          if (!it.code.trim()) throw new Error(`备注模板 code 不能为空(${m.label})`);
          if (!it.label.trim()) throw new Error(`备注模板 label 不能为空(${m.label})`);
          if (!it.walletPoolId) throw new Error(`备注模板 ${it.label} 必须选资金池`);
        }
      }
      return pushXboxWalletSettings(
        methods.map((m) => ({
          code: m.code.trim(),
          label: m.label.trim(),
          items: m.items.map((it) => ({
            code: it.code.trim(),
            label: it.label.trim(),
            walletPoolId: it.walletPoolId,
            isActive: it.isActive
          }))
        }))
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-wallet-settings"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-3xl max-h-[90vh] flex flex-col">
        <CardHeader>
          <CardTitle>编辑钱包设置</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            收款方式 → 备注模板 → 资金池(具体钱包)。保存即全量同步。
          </div>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto space-y-4">
          {methods.map((m, mIdx) => (
            <Card key={mIdx} className="border-2">
              <CardContent className="p-3 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <input
                    className="h-9 rounded-md border border-border bg-card px-3 text-sm outline-none"
                    value={m.code}
                    onChange={(e) => updateMethod(mIdx, "code", e.target.value)}
                    placeholder="code 如 agent"
                  />
                  <input
                    className="h-9 rounded-md border border-border bg-card px-3 text-sm outline-none col-span-1"
                    value={m.label}
                    onChange={(e) => updateMethod(mIdx, "label", e.target.value)}
                    placeholder="label 如 代理"
                  />
                  <Button variant="ghost" size="sm" onClick={() => removeMethod(mIdx)} className="text-red-600">
                    删除收款方式
                  </Button>
                </div>
                <div className="ml-4 space-y-1">
                  <div className="text-xs text-muted-foreground">备注模板</div>
                  {m.items.map((it, iIdx) => {
                    const idx = buildPoolWalletIndex(poolGroups);
                    const pool = idx.get(it.walletPoolId);
                    return (
                      <div key={iIdx} className="grid grid-cols-12 gap-1 items-center">
                        <input
                          className="col-span-2 h-8 rounded-md border border-border bg-card px-2 text-xs"
                          value={it.code}
                          onChange={(e) => updateItem(mIdx, iIdx, "code", e.target.value)}
                          placeholder="code"
                        />
                        <input
                          className="col-span-3 h-8 rounded-md border border-border bg-card px-2 text-xs"
                          value={it.label}
                          onChange={(e) => updateItem(mIdx, iIdx, "label", e.target.value)}
                          placeholder="label"
                        />
                        <select
                          className="col-span-5 h-8 rounded-md border border-border bg-card px-2 text-xs"
                          value={it.walletPoolId}
                          onChange={(e) => updateItem(mIdx, iIdx, "walletPoolId", e.target.value)}
                        >
                          <option value="">-- 资金池 --</option>
                          {poolGroups.map((g) => (
                            <optgroup key={g.groupCode} label={`── ${g.groupLabel} ──`}>
                              {g.wallets.map((w) => (
                                <option key={w.id} value={w.id}>
                                  {w.fullPath} ({w.currency})
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                        <span className="col-span-1 text-xs text-muted-foreground truncate">
                          {pool?.currency ?? ""}
                        </span>
                        <Button variant="ghost" size="sm" onClick={() => removeItem(mIdx, iIdx)} className="col-span-1 text-red-600">
                          删
                        </Button>
                      </div>
                    );
                  })}
                  <Button variant="outline" size="sm" onClick={() => addItem(mIdx)}>
                    <Plus className="h-3 w-3" />
                    加备注模板
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
          <Button variant="outline" onClick={addMethod}>
            <Plus className="h-4 w-4" />
            加收款方式
          </Button>

          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}
        </CardContent>
        <div className="border-t border-border p-3 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            取消
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "保存中..." : "全量同步"}
          </Button>
        </div>
      </Card>
    </div>
  );
}

function WalletSettingsTab() {
  const [showEdit, setShowEdit] = useState(false);

  const { data: methods = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-wallet-settings"],
    queryFn: () => getXboxWalletSettings(false)
  });
  const { data: poolGroups = [] } = useQuery({
    queryKey: ["xbox-wallet-pool-options"],
    queryFn: () => getXboxWalletPoolOptions()
  });

  const poolIndex = buildPoolWalletIndex(poolGroups);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          财务系统钱包设置:收款方式 → 备注模板 → 资金池(可挂任何钱包：资产/淘宝/台湾/...)
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            刷新
          </Button>
          <Button size="sm" onClick={() => setShowEdit(true)}>
            <Pencil className="h-4 w-4" />
            编辑
          </Button>
        </div>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>收款方式</TableHead>
                <TableHead>备注模板</TableHead>
                <TableHead>资金池所属</TableHead>
                <TableHead>资金池</TableHead>
                <TableHead>状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {methods.flatMap((m) =>
                m.items.length === 0
                  ? [
                      <TableRow key={m.id}>
                        <TableCell className="font-medium">{m.label}</TableCell>
                        <TableCell colSpan={4} className="text-xs text-muted-foreground">
                          (无备注模板)
                        </TableCell>
                      </TableRow>
                    ]
                  : m.items.map((it, idx) => {
                      const pool = poolIndex.get(it.walletPoolId);
                      return (
                        <TableRow key={`${m.id}-${it.id}`}>
                          <TableCell className={cn("font-medium", idx > 0 && "text-transparent")}>
                            {m.label}
                          </TableCell>
                          <TableCell>
                            {it.label}
                            <span className="ml-2 text-xs text-muted-foreground tabular-nums">
                              ({it.code})
                            </span>
                          </TableCell>
                          <TableCell>
                            {pool ? (
                              <Badge tone="transfer">{pool.groupLabel}</Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">未知</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs">
                            {pool
                              ? `${pool.fullPath} (${pool.currency})`
                              : `wallet#${it.walletPoolId}`}
                          </TableCell>
                          <TableCell>
                            <Badge tone={it.isActive ? "success" : "neutral"}>
                              {it.isActive ? "启用" : "停用"}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      );
                    })
              )}
              {methods.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    还没设钱包设置。点右上角「编辑」开始配置。
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {showEdit ? (
        <WalletSettingsEditModal
          initial={methods}
          poolGroups={poolGroups}
          onClose={() => setShowEdit(false)}
        />
      ) : null}
    </div>
  );
}


type XboxTab = "accounts" | "orders" | "sale-records" | "wallet-settings" | "reconcile";

const TAB_META: { id: XboxTab; label: string; icon: React.ReactNode }[] = [
  { id: "accounts", label: "账号管理", icon: <Users className="h-4 w-4" /> },
  { id: "orders", label: "订单", icon: <Receipt className="h-4 w-4" /> },
  { id: "sale-records", label: "销售记录", icon: <Layers className="h-4 w-4" /> },
  { id: "wallet-settings", label: "钱包设置", icon: <Settings2 className="h-4 w-4" /> },
  { id: "reconcile", label: "对账", icon: <GitCompare className="h-4 w-4" /> }
];


// ===================================================================
// 对账 Tab（CEO 2026-05-08 Q1A+Q2A+Q3A+Q4A）
// ===================================================================

function ReconcileTab() {
  const queryClient = useQueryClient();
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [showAddMapping, setShowAddMapping] = useState<{ theoreticalWalletId: string } | null>(null);

  const { data: poolGroupsXbox = [] } = useQuery({
    queryKey: ["xbox-pool-options-only"],
    queryFn: () => getXboxWalletPoolOptions({ xboxOnly: true })
  });
  const { data: poolGroupsAll = [] } = useQuery({
    queryKey: ["xbox-pool-options-all-with-groups"],
    // 含 group 钱包(店铺总钱包),让 CEO 能选总钱包当映射目标
    queryFn: () => getXboxWalletPoolOptions({ xboxOnly: false, includeGroups: true })
  });
  const { data: mappings = [], refetch: refetchMappings } = useQuery({
    queryKey: ["xbox-reconcile-mappings"],
    queryFn: getXboxReconcileMappings
  });
  const { data: report = [], isFetching, refetch: refetchReport } = useQuery({
    queryKey: ["xbox-reconcile-report", date],
    queryFn: () => getXboxReconcileReport(date)
  });

  // 理论值钱包列表（XBOX_SALES_LEDGER 大类的叶子）
  const theoreticalWallets = poolGroupsXbox.flatMap((g) => g.wallets);
  // 实际值钱包列表（除 XBOX_SALES_LEDGER 大类之外）
  const actualGroups = poolGroupsAll.filter((g) => g.groupCode !== "XBOX_SALES_LEDGER");

  const idx = buildPoolWalletIndex(poolGroupsAll);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">对账日期</span>
          <input
            type="date"
            className="h-9 rounded border border-border bg-card px-2 text-sm"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <Button variant="outline" size="sm" onClick={() => refetchReport()} disabled={isFetching}>
          <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          刷新对账
        </Button>
      </div>

      {/* 对账报告 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{date} 对账</CardTitle>
          <div className="text-xs text-muted-foreground">
            理论值（XBOX 销售归口）当日流入 vs 实际值钱包当日 IN 流水。差异 ≠ 0 表示客服可能填错出售渠道,
            可在订单 tab 用「改字段」拆单纠错。
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>理论值钱包</TableHead>
                <TableHead>币种</TableHead>
                <TableHead className="text-right">理论金额</TableHead>
                <TableHead className="text-right">实际金额（合计）</TableHead>
                <TableHead className="text-right">差异</TableHead>
                <TableHead>映射的实际钱包</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.map((row) => {
                const diff = Number(row.diff);
                const diffColor =
                  diff === 0 ? "text-muted-foreground" : diff > 0 ? "text-blue-600" : "text-red-600";
                return (
                  <TableRow key={row.theoreticalWallet.id}>
                    <TableCell className="font-medium">{row.theoreticalWallet.name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.theoreticalWallet.currency}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(row.theoreticalTotal).toLocaleString("zh-CN", {
                        minimumFractionDigits: 2, maximumFractionDigits: 2
                      })}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(row.actualTotal).toLocaleString("zh-CN", {
                        minimumFractionDigits: 2, maximumFractionDigits: 2
                      })}
                    </TableCell>
                    <TableCell className={cn("text-right tabular-nums font-semibold", diffColor)}>
                      {diff > 0 ? "+" : ""}
                      {Number(row.diff).toLocaleString("zh-CN", {
                        minimumFractionDigits: 2, maximumFractionDigits: 2
                      })}
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.actualWallets.length === 0 ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setShowAddMapping({
                            theoreticalWalletId: String(row.theoreticalWallet.id)
                          })}
                        >
                          <Plus className="h-3 w-3" />
                          加映射
                        </Button>
                      ) : (
                        <div className="flex flex-wrap gap-1 items-center">
                          {row.actualWallets.map((aw) => {
                            const mapping = mappings.find(
                              (m) =>
                                m.theoreticalWalletId === String(row.theoreticalWallet.id) &&
                                m.actualWalletId === String(aw.id)
                            );
                            return (
                              <Badge key={aw.id} tone="transfer">
                                <span>{aw.name}</span>
                                <span className="ml-1 tabular-nums">
                                  ({aw.currency} {Number(aw.total).toLocaleString("zh-CN")})
                                </span>
                                {mapping ? (
                                  <button
                                    type="button"
                                    className="ml-1 hover:text-red-600"
                                    onClick={async () => {
                                      if (confirm(`删除映射 ${row.theoreticalWallet.name} ↔ ${aw.name}?`)) {
                                        await deleteXboxReconcileMapping(mapping.id);
                                        refetchMappings();
                                        refetchReport();
                                      }
                                    }}
                                  >
                                    <Trash2 className="h-3 w-3 inline" />
                                  </button>
                                ) : null}
                              </Badge>
                            );
                          })}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setShowAddMapping({
                              theoreticalWalletId: String(row.theoreticalWallet.id)
                            })}
                          >
                            <Link2 className="h-3 w-3" />
                            加
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
              {report.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    暂无对账数据
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {showAddMapping ? (
        <AddMappingModal
          theoreticalWalletId={showAddMapping.theoreticalWalletId}
          theoreticalWallets={theoreticalWallets}
          actualGroups={actualGroups}
          onClose={() => setShowAddMapping(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["xbox-reconcile-mappings"] });
            queryClient.invalidateQueries({ queryKey: ["xbox-reconcile-report"] });
          }}
        />
      ) : null}
    </div>
  );
}

function AddMappingModal({
  theoreticalWalletId,
  theoreticalWallets,
  actualGroups,
  onClose,
  onSuccess
}: {
  theoreticalWalletId: string;
  theoreticalWallets: { id: string; name: string; currency: string }[];
  actualGroups: XboxPoolOptionGroup[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [actualWalletId, setActualWalletId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const theoretical = theoreticalWallets.find((w) => w.id === theoreticalWalletId);
  // 只显示币种相同的实际钱包
  const compatibleGroups = actualGroups
    .map((g) => ({
      ...g,
      wallets: g.wallets.filter((w) => w.currency === theoretical?.currency)
    }))
    .filter((g) => g.wallets.length > 0);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!actualWalletId) throw new Error("请选实际钱包");
      return createXboxReconcileMapping({
        theoreticalWalletId,
        actualWalletId
      });
    },
    onSuccess: () => {
      onSuccess();
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "创建失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>添加对账映射</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            理论值钱包: {theoretical?.name} ({theoretical?.currency})
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">关联到实际钱包（仅显示同币种）</div>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={actualWalletId}
              onChange={(e) => setActualWalletId(e.target.value)}
            >
              <option value="">-- 选实际钱包 --</option>
              {compatibleGroups.map((g) => (
                <optgroup key={g.groupCode} label={`── ${g.groupLabel} ──`}>
                  {g.wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.fullPath}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {error ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>取消</Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? "添加中..." : "添加"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AccountsManagementTab() {
  const queryClient = useQueryClient();
  const [country, setCountry] = useState<XboxCountry>("US");
  const [showCreate, setShowCreate] = useState(false);
  const [transactionsTarget, setTransactionsTarget] = useState<XboxAccount | null>(null);
  const [editTarget, setEditTarget] = useState<XboxAccount | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<XboxAccount | null>(null);
  const [statusTarget, setStatusTarget] = useState<XboxAccount | null>(null);
  const [auditTarget, setAuditTarget] = useState<XboxAccount | null>(null);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);

  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-accounts", country],
    queryFn: () => getXboxAccounts(country)
  });

  // CEO 后台需要的领取数据 + 客服字典
  const { data: claims = [] } = useQuery({
    queryKey: ["operator-claims-all", true],
    queryFn: () => getAllClaims(true)
  });
  const { data: operators = [] } = useQuery({
    queryKey: ["operators"],
    queryFn: getOperators
  });
  const claimByAccountId = new Map(
    claims.map((c) => [c.accountId, { id: c.id, operatorId: c.operatorId }])
  );
  const operatorById = new Map(
    operators.map((o) => [
      o.id,
      { id: o.id, displayName: o.displayName, loginName: o.loginName }
    ])
  );

  const toggleAvailabilityMut = useMutation({
    mutationFn: (account: XboxAccount) =>
      patchXboxAccountAvailability(account.id, !account.isAvailableForClaim),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (err) =>
      setAvailabilityError(err instanceof Error ? err.message : "标记失败")
  });

  const recallMut = useMutation({
    mutationFn: (claimId: number) => returnClaim(claimId, { forceRecall: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-claims-all"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (err) =>
      setAvailabilityError(err instanceof Error ? err.message : "强制回收失败")
  });

  // CEO 2026-05-12 Q2: 单账号刷新余额(用于判断出入库)
  const refreshOneMut = useMutation({
    mutationFn: (accountId: string) => refreshXboxAccountBalance(accountId),
    onSuccess: async () => {
      setAvailabilityError(null);
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (err) =>
      setAvailabilityError(err instanceof Error ? err.message : "刷新余额失败")
  });

  // CEO 2026-05-12 Q2: 全部刷新余额(批量)
  const refreshAllMut = useMutation({
    mutationFn: () => refreshAllXboxBalances(),
    onSuccess: async (result) => {
      setAvailabilityError(null);
      setRefreshAllSummary(
        `刷新完成: ${result.succeeded}/${result.total} 个账号余额已更新${result.failed ? `, ${result.failed} 个失败(账号未设密码/已停用)` : ""}`
      );
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (err) =>
      setAvailabilityError(err instanceof Error ? err.message : "全部刷新失败")
  });
  const [refreshAllSummary, setRefreshAllSummary] = useState<string | null>(null);

  const meta = COUNTRY_META[country];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
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
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setRefreshAllSummary(null);
              if (
                confirm(
                  "全部刷新余额? 将串行向 Microsoft 拉取所有 active 账号的最新余额(每个账号约 2-3 秒)。"
                )
              ) {
                refreshAllMut.mutate();
              }
            }}
            disabled={refreshAllMut.isPending}
            title="批量刷新 → 判断哪些账号正在被使用(余额变了 = 客服在消费)"
          >
            <RefreshCcw className={cn("h-4 w-4", refreshAllMut.isPending && "animate-spin")} />
            {refreshAllMut.isPending ? "全部刷新中…" : "全部刷新余额"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            刷新列表
          </Button>
        </div>
      </div>

      {refreshAllSummary ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          {refreshAllSummary}
        </div>
      ) : null}

      <SummaryCards country={country} />

      {availabilityError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {availabilityError}
        </div>
      ) : null}

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
            claimByAccountId={claimByAccountId}
            operatorById={operatorById}
            onTransactions={setTransactionsTarget}
            onEdit={setEditTarget}
            onChangePassword={setPasswordTarget}
            onChangeStatus={setStatusTarget}
            onShowAuditLogs={setAuditTarget}
            onToggleAvailable={(account) => {
              setAvailabilityError(null);
              const next = !account.isAvailableForClaim;
              if (
                confirm(
                  next
                    ? `把账号「${account.accountNo ?? account.name}」标为可出库？客服可以从客服 exe 领取此账号。`
                    : `撤销账号「${account.accountNo ?? account.name}」的可出库状态？客服将无法再领取此账号（已领取的不受影响）。`
                )
              ) {
                toggleAvailabilityMut.mutate(account);
              }
            }}
            onForceRecall={(claimId, accountLabel, holderName) => {
              setAvailabilityError(null);
              if (
                confirm(
                  `强制回收账号「${accountLabel}」(当前由「${holderName}」持有)？回收后该账号回到可领池子。`
                )
              ) {
                recallMut.mutate(claimId);
              }
            }}
            togglePending={toggleAvailabilityMut.isPending}
            recallPending={recallMut.isPending}
            onRefreshBalance={(account) => {
              setRefreshAllSummary(null);
              refreshOneMut.mutate(account.id);
            }}
            refreshingAccountId={refreshOneMut.variables ?? null}
            refreshPending={refreshOneMut.isPending}
          />
        </CardContent>
      </Card>

      {showCreate ? (
        <CreateAccountModal defaultCountry={country} onClose={() => setShowCreate(false)} />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal account={transactionsTarget} onClose={() => setTransactionsTarget(null)} />
      ) : null}
      {editTarget ? (
        <EditAccountModal account={editTarget} onClose={() => setEditTarget(null)} />
      ) : null}
      {passwordTarget ? (
        <ChangePasswordModal account={passwordTarget} onClose={() => setPasswordTarget(null)} />
      ) : null}
      {statusTarget ? (
        <ChangeStatusModal account={statusTarget} onClose={() => setStatusTarget(null)} />
      ) : null}
      {auditTarget ? (
        <AuditLogsModal account={auditTarget} onClose={() => setAuditTarget(null)} />
      ) : null}
    </div>
  );
}

export function XboxPage() {
  const [tab, setTab] = useState<XboxTab>("accounts");
  const [highlightSaleRecordId, setHighlightSaleRecordId] = useState<string | null>(null);

  // 跳转到销售记录 tab 并高亮某条
  const jumpToSaleRecord = (id: string) => {
    setHighlightSaleRecordId(id);
    setTab("sale-records");
    // 5 秒后自动取消高亮
    setTimeout(() => setHighlightSaleRecordId(null), 5000);
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold tracking-normal">XBOX</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          XBOX 账号库存 / 同步订单 / 销售记录 / 钱包设置 — 完整业务链路
        </p>
      </div>

      <div className="inline-flex rounded-md border border-border p-1">
        {TAB_META.map((t) => (
          <button
            key={t.id}
            type="button"
            className={cn(
              "h-9 px-4 rounded text-sm font-medium text-muted-foreground transition-colors flex items-center gap-1.5",
              tab === t.id && "bg-muted text-foreground"
            )}
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {tab === "accounts" ? <AccountsManagementTab /> : null}
      {tab === "orders" ? <OrdersTab onJumpToSaleRecord={jumpToSaleRecord} /> : null}
      {tab === "sale-records" ? <SaleRecordsTab highlightId={highlightSaleRecordId} /> : null}
      {tab === "wallet-settings" ? <WalletSettingsTab /> : null}
      {tab === "reconcile" ? <ReconcileTab /> : null}
    </div>
  );
}
