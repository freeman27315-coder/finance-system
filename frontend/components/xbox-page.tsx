"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Gamepad2,
  History,
  KeyRound,
  Layers,
  ListOrdered,
  Pencil,
  Plus,
  Receipt,
  RefreshCcw,
  Settings2,
  ShieldAlert,
  Users
} from "lucide-react";
import { useState } from "react";
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
  getXboxAccountAuditLogs,
  getXboxAccounts,
  getXboxOrderChangeLogs,
  getXboxOrders,
  getXboxSaleRecordChangeLogs,
  getXboxSaleRecords,
  getXboxSummary,
  getXboxTransactions,
  getXboxWalletPoolOptions,
  getXboxWalletSettings,
  patchXboxOrder,
  patchXboxSaleRecord,
  pushXboxWalletSettings,
  rechargeXbox,
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
  defaultCountry,
  onClose
}: {
  defaultCountry: XboxCountry;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [country, setCountry] = useState<XboxCountry>(defaultCountry);
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
      return createXboxAccount({
        // 后端 name 字段必填,直接用账号编号当 name 传过去
        name: trimmedAccountNo,
        country,
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
  onTransactions,
  onEdit,
  onChangePassword,
  onChangeStatus,
  onShowAuditLogs
}: {
  accounts: XboxAccount[];
  country: XboxCountry;
  onTransactions: (account: XboxAccount) => void;
  onEdit: (account: XboxAccount) => void;
  onChangePassword: (account: XboxAccount) => void;
  onChangeStatus: (account: XboxAccount) => void;
  onShowAuditLogs: (account: XboxAccount) => void;
}) {
  const meta = COUNTRY_META[country];
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>账号编号</TableHead>
          <TableHead>登录邮箱</TableHead>
          <TableHead>状态</TableHead>
          <TableHead className="text-right">RMB 累计成本</TableHead>
          <TableHead className="text-right">本地余额</TableHead>
          <TableHead>备注</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accounts.map((account) => (
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
              <div className="flex flex-col gap-0.5">
                <StatusBadge status={account.status} />
                {account.statusMessage ? (
                  <span className="text-[10px] text-muted-foreground truncate max-w-[120px]">
                    {account.statusMessage}
                  </span>
                ) : null}
              </div>
            </TableCell>
            <TableCell className="text-right tabular-nums text-red-600">
              {formatMoney(account.rmbCostMinor, "CNY")}
            </TableCell>
            <TableCell className={cn("text-right tabular-nums font-semibold", meta.accentText)}>
              {formatMoney(account.localBalanceMinor, account.currency)}
            </TableCell>
            <TableCell className="text-muted-foreground text-xs">{account.remark ?? "-"}</TableCell>
            <TableCell className="text-right">
              <div className="flex flex-wrap justify-end gap-1">
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
        ))}
        {accounts.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
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
  const [saleDate, setSaleDate] = useState(
    order.saleDate ?? new Date().toISOString().slice(0, 10)
  );
  const [productName, setProductName] = useState(order.productName ?? "");
  const [operatorName, setOperatorName] = useState(order.operatorName ?? "");
  const [salePrice, setSalePrice] = useState("");
  const [saleCurrency, setSaleCurrency] = useState<XboxSaleCurrency>(
    order.saleCurrency ?? "CNY"
  );
  const [walletMethodId, setWalletMethodId] = useState(order.walletMethodId ?? "");
  const [walletItemId, setWalletItemId] = useState(order.walletItemId ?? "");
  const [error, setError] = useState<string | null>(null);

  const account = accounts.find((a) => a.id === order.accountId);
  const selectedMethod = walletMethods.find((m) => m.id === walletMethodId);
  const itemOptions = selectedMethod?.items ?? [];

  const mutation = useMutation({
    mutationFn: async () => {
      if (!productName.trim()) throw new Error("商品名不能为空");
      if (!operatorName.trim()) throw new Error("经办人不能为空");
      if (!salePrice.trim()) throw new Error("售价不能为空");
      if (!walletMethodId) throw new Error("请选收款方式");
      if (!walletItemId) throw new Error("请选备注模板");
      return patchXboxOrder(order.id, {
        saleDate,
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
      await queryClient.invalidateQueries({ queryKey: ["asset-wallets"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "保存失败")
  });

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
            <div className="text-sm text-muted-foreground">销售日期 *</div>
            <input
              type="date"
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={saleDate}
              onChange={(event) => setSaleDate(event.target.value)}
            />
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
          <div className="rounded-md bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-700">
            填齐后保存,系统自动生成销售记录 + 售价进对应资金池
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

function OrdersTab() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [completeTarget, setCompleteTarget] = useState<XboxOrder | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "pending_complete" | "converted">("all");
  const [logsTarget, setLogsTarget] = useState<XboxOrder | null>(null);

  const { data: accounts = [] } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const { data: orders = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-orders", statusFilter],
    queryFn: () =>
      getXboxOrders(
        statusFilter === "all" ? undefined : { status: statusFilter }
      )
  });
  const { data: walletMethods = [] } = useQuery({
    queryKey: ["xbox-wallet-settings"],
    queryFn: () => getXboxWalletSettings(true)
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
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
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            刷新
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
                          <Badge tone="success">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            已转销售
                          </Badge>
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

function SaleRecordsTab() {
  const [editTarget, setEditTarget] = useState<XboxSaleRecord | null>(null);
  const [expandTarget, setExpandTarget] = useState<XboxSaleRecord | null>(null);
  const [logsTarget, setLogsTarget] = useState<XboxSaleRecord | null>(null);

  const { data: records = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-sale-records"],
    queryFn: () => getXboxSaleRecords()
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const { data: walletMethods = [] } = useQuery({
    queryKey: ["xbox-wallet-settings"],
    queryFn: () => getXboxWalletSettings(true)
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          刷新
        </Button>
      </div>
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
                return (
                  <TableRow key={record.id}>
                    <TableCell className="text-xs tabular-nums">{record.saleDate}</TableCell>
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


type XboxTab = "accounts" | "orders" | "sale-records" | "wallet-settings";

const TAB_META: { id: XboxTab; label: string; icon: React.ReactNode }[] = [
  { id: "accounts", label: "账号管理", icon: <Users className="h-4 w-4" /> },
  { id: "orders", label: "订单", icon: <Receipt className="h-4 w-4" /> },
  { id: "sale-records", label: "销售记录", icon: <Layers className="h-4 w-4" /> },
  { id: "wallet-settings", label: "钱包设置", icon: <Settings2 className="h-4 w-4" /> }
];

function AccountsManagementTab() {
  const [country, setCountry] = useState<XboxCountry>("US");
  const [showCreate, setShowCreate] = useState(false);
  const [transactionsTarget, setTransactionsTarget] = useState<XboxAccount | null>(null);
  const [editTarget, setEditTarget] = useState<XboxAccount | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<XboxAccount | null>(null);
  const [statusTarget, setStatusTarget] = useState<XboxAccount | null>(null);
  const [auditTarget, setAuditTarget] = useState<XboxAccount | null>(null);

  const { data: accounts = [], isFetching, refetch } = useQuery({
    queryKey: ["xbox-accounts", country],
    queryFn: () => getXboxAccounts(country)
  });

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
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          刷新账号
        </Button>
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
            onTransactions={setTransactionsTarget}
            onEdit={setEditTarget}
            onChangePassword={setPasswordTarget}
            onChangeStatus={setStatusTarget}
            onShowAuditLogs={setAuditTarget}
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
      {tab === "orders" ? <OrdersTab /> : null}
      {tab === "sale-records" ? <SaleRecordsTab /> : null}
      {tab === "wallet-settings" ? <WalletSettingsTab /> : null}
    </div>
  );
}
