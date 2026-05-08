"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Gamepad2,
  History,
  KeyRound,
  ListOrdered,
  Pencil,
  Plus,
  RefreshCcw,
  ShieldAlert
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
  getXboxAccountAuditLogs,
  getXboxAccounts,
  getXboxSummary,
  getXboxTransactions,
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
  XboxCountry
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
  const [loginEmail, setLoginEmail] = useState(account.loginEmail ?? "");
  const [exchangeRate, setExchangeRate] = useState(
    account.exchangeRate != null ? String(account.exchangeRate) : ""
  );
  const [remark, setRemark] = useState(account.remark ?? "");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () =>
      // 不传 name 字段（后端不变更）。账号编号是不可变主标识,目前也不在此处编辑
      updateXboxAccount(account.id, {
        loginEmail: loginEmail.trim(),
        exchangeRate: exchangeRate.trim() === "" ? "" : exchangeRate.trim(),
        remark: remark
      }),
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
            <TableCell className="font-medium">
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

export function XboxPage() {
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
