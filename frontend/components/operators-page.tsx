"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Eye,
  KeyRound,
  Pause,
  Play,
  Plus,
  QrCode,
  RefreshCcw,
  ShieldCheck,
  Users,
  X
} from "lucide-react";
import { useState } from "react";
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
  confirmOperatorTotp,
  createOperator,
  deactivateOperator,
  getAllClaims,
  getOperatorTotpQr,
  getOperators,
  getXboxAccounts,
  reactivateOperator,
  returnClaim
} from "@/lib/api";
import type { Operator, OperatorClaim, OperatorTotpSetup, XboxAccount } from "@/types";

function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

// ===================================================================
// 创建客服 Modal -> 自动弹出 TOTP 绑定
// ===================================================================

function CreateOperatorModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [loginName, setLoginName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [remark, setRemark] = useState("");
  const [setup, setSetup] = useState<OperatorTotpSetup | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: async () => {
      if (!loginName.trim() || !displayName.trim() || !password.trim()) {
        throw new Error("登录名 / 显示名 / 密码均必填");
      }
      if (password.length < 6) throw new Error("密码至少 6 位");
      return createOperator({
        loginName: loginName.trim(),
        displayName: displayName.trim(),
        password,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async (data) => {
      setSetup(data);
      await queryClient.invalidateQueries({ queryKey: ["operators"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "创建失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{setup ? "扫码绑定 TOTP" : "新建客服"}</CardTitle>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {setup ? (
            <TotpSetupView setup={setup} onDone={onClose} />
          ) : (
            <>
              <div className="space-y-1">
                <label className="text-xs font-medium">
                  登录名 <span className="text-red-600">*</span>
                </label>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  placeholder="如 zhang_san"
                  value={loginName}
                  onChange={(e) => setLoginName(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">
                  显示名 <span className="text-red-600">*</span>
                </label>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  placeholder="如 张三"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">
                  密码 <span className="text-red-600">*</span>
                  <span className="ml-1 text-muted-foreground">（≥6 位）</span>
                </label>
                <input
                  type="password"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">备注</label>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  placeholder="可选"
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                />
              </div>
              {error ? <div className="text-xs text-red-600">{error}</div> : null}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={onClose}>
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    setError(null);
                    createMut.mutate();
                  }}
                  disabled={createMut.isPending}
                >
                  {createMut.isPending ? "创建中…" : "创建客服"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ===================================================================
// TOTP 绑定视图：二维码 + secret + 6 位验证码
// ===================================================================

function TotpSetupView({
  setup,
  onDone
}: {
  setup: OperatorTotpSetup;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const confirmMut = useMutation({
    mutationFn: async () => {
      if (code.length !== 6 || !/^\d{6}$/.test(code)) {
        throw new Error("请输入 6 位数字验证码");
      }
      return confirmOperatorTotp(setup.operatorId, code);
    },
    onSuccess: async () => {
      setConfirmed(true);
      await queryClient.invalidateQueries({ queryKey: ["operators"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "校验失败")
  });

  if (confirmed) {
    return (
      <div className="space-y-3 text-center">
        <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" />
        <div className="text-sm font-medium">TOTP 绑定成功</div>
        <div className="text-xs text-muted-foreground">
          客服可以用「登录名 + 密码 + 6 位 TOTP」登录了。
        </div>
        <Button size="sm" onClick={onDone}>
          完成
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
        把下方二维码发给客服 → 用 Google Authenticator / Authy 扫码 → 输入 6 位验证码确认绑定。
        <br />
        <strong>关键：</strong>客服必须完成扫码确认才能登录。本页关闭后可在客服列表点
        <QrCode className="inline h-3 w-3" /> 重看二维码。
      </div>
      <div className="flex justify-center">
        <img
          src={`data:image/png;base64,${setup.totpQrPngBase64}`}
          alt="TOTP QR Code"
          className="h-48 w-48 border border-border bg-white p-1"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">TOTP Secret（备份，可手动输入到 App）</label>
        <div className="rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs break-all">
          {setup.totpSecret}
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">
          6 位验证码 <span className="text-red-600">*</span>
        </label>
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-center font-mono text-lg tracking-widest"
          placeholder="000000"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        />
      </div>
      {error ? <div className="text-xs text-red-600">{error}</div> : null}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onDone}>
          稍后绑定
        </Button>
        <Button
          size="sm"
          onClick={() => {
            setError(null);
            confirmMut.mutate();
          }}
          disabled={confirmMut.isPending}
        >
          {confirmMut.isPending ? "校验中…" : "确认绑定"}
        </Button>
      </div>
    </div>
  );
}

// ===================================================================
// 重看 TOTP 二维码 Modal（客服扔了二维码可重新看）
// ===================================================================

function RebindTotpModal({
  operator,
  onClose
}: {
  operator: Operator;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["operator-totp-qr", operator.id],
    queryFn: () => getOperatorTotpQr(operator.id)
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>
            {operator.displayName} · {operator.totpConfirmed ? "已绑定 TOTP" : "重看绑定二维码"}
          </CardTitle>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading || !data ? (
            <div className="py-8 text-center text-sm text-muted-foreground">加载中…</div>
          ) : (
            <TotpSetupView setup={data} onDone={onClose} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ===================================================================
// 当前活跃领取列表（CEO 后台看「谁领了哪个号」+ 强制回收）
// ===================================================================

function ClaimsPanel({
  operators,
  accounts
}: {
  operators: Operator[];
  accounts: XboxAccount[];
}) {
  const queryClient = useQueryClient();
  const claimsQuery = useQuery({
    queryKey: ["operator-claims-all", true],
    queryFn: () => getAllClaims(true)
  });
  const [recallError, setRecallError] = useState<string | null>(null);

  const recallMut = useMutation({
    mutationFn: (claimId: number) => returnClaim(claimId, { forceRecall: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-claims-all"] });
      await queryClient.invalidateQueries({ queryKey: ["xbox-accounts"] });
    },
    onError: (err) => setRecallError(err instanceof Error ? err.message : "回收失败")
  });

  const opById = new Map(operators.map((o) => [o.id, o]));
  const accById = new Map(accounts.map((a) => [Number(a.id), a]));

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>当前账号领取状态</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            每个客服同时最多领 3 个账号，1 个账号同时只能被 1 个客服持有。
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => claimsQuery.refetch()}
          disabled={claimsQuery.isFetching}
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {recallError ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {recallError}
          </div>
        ) : null}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账号</TableHead>
              <TableHead>持有客服</TableHead>
              <TableHead>领取时间</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(claimsQuery.data ?? []).map((claim: OperatorClaim) => {
              const acc = accById.get(claim.accountId);
              const op = opById.get(claim.operatorId);
              return (
                <TableRow key={claim.id}>
                  <TableCell className="text-xs">
                    {acc ? acc.accountNo ?? acc.name : `#${claim.accountId}`}
                    <div className="text-[10px] text-muted-foreground">
                      {acc?.loginEmail ?? "-"}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {op ? (
                      <>
                        <div className="font-medium">{op.displayName}</div>
                        <div className="text-[10px] text-muted-foreground">{op.loginName}</div>
                      </>
                    ) : (
                      `#${claim.operatorId}`
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
                    {formatDateTime(claim.claimedAt)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setRecallError(null);
                        if (
                          confirm(
                            `强制回收账号「${acc?.accountNo ?? acc?.name ?? `#${claim.accountId}`}」(${op?.displayName ?? "未知"} 持有)？`
                          )
                        ) {
                          recallMut.mutate(claim.id);
                        }
                      }}
                      disabled={recallMut.isPending}
                    >
                      强制回收
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {(claimsQuery.data ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                  暂无活跃领取
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ===================================================================
// 主页面
// ===================================================================

export function OperatorsPage() {
  const queryClient = useQueryClient();
  const operatorsQuery = useQuery({
    queryKey: ["operators"],
    queryFn: getOperators
  });
  const accountsQuery = useQuery({
    queryKey: ["xbox-accounts"],
    queryFn: () => getXboxAccounts()
  });
  const [showCreate, setShowCreate] = useState(false);
  const [rebindTarget, setRebindTarget] = useState<Operator | null>(null);

  const toggleMut = useMutation({
    mutationFn: async (op: Operator) => {
      return op.isActive ? deactivateOperator(op.id) : reactivateOperator(op.id);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operators"] });
    }
  });

  const operators = operatorsQuery.data ?? [];
  const accounts = accountsQuery.data ?? [];
  const activeCount = operators.filter((o) => o.isActive).length;
  const totpDoneCount = operators.filter((o) => o.totpConfirmed).length;
  const availableForClaimCount = accounts.filter((a) => a.isAvailableForClaim).length;

  return (
    <div className="space-y-5">
      {/* ----- 概览卡 ----- */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs text-muted-foreground">客服总数</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tabular-nums">{operators.length}</span>
              <span className="text-xs text-muted-foreground">活跃 {activeCount}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs text-muted-foreground">已绑定 TOTP</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tabular-nums">{totpDoneCount}</span>
              <span className="text-xs text-muted-foreground">/ {operators.length}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs text-muted-foreground">已标"可出库"账号</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tabular-nums text-emerald-700">
                {availableForClaimCount}
              </span>
              <span className="text-xs text-muted-foreground">/ {accounts.length}</span>
            </div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              在 XBOX 页签按账号标记
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ----- 客服列表 ----- */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              客服管理
            </CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              登录三要素 = 登录名 + 密码 + Google/Authy TOTP 6 位
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => operatorsQuery.refetch()}
              disabled={operatorsQuery.isFetching}
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              刷新
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-3.5 w-3.5" />
              新建客服
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>登录名</TableHead>
                <TableHead>显示名</TableHead>
                <TableHead>TOTP 绑定</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>备注</TableHead>
                <TableHead>最近登录</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {operators.map((op) => (
                <TableRow key={op.id}>
                  <TableCell className="font-mono text-xs">{op.loginName}</TableCell>
                  <TableCell className="text-sm">{op.displayName}</TableCell>
                  <TableCell>
                    {op.totpConfirmed ? (
                      <Badge tone="success">
                        <ShieldCheck className="mr-1 h-3 w-3" />
                        已绑定
                      </Badge>
                    ) : (
                      <Badge tone="warning">
                        <KeyRound className="mr-1 h-3 w-3" />
                        未绑定
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {op.isActive ? (
                      <Badge tone="neutral">活跃</Badge>
                    ) : (
                      <Badge tone="danger">已停用</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {op.remark ?? "-"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
                    {formatDateTime(op.lastLoginAt)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRebindTarget(op)}
                        title="重看 TOTP 二维码 / 重新绑定"
                      >
                        <QrCode className="h-3.5 w-3.5" />
                        TOTP
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (
                            confirm(
                              op.isActive
                                ? `停用客服「${op.displayName}」？停用后无法登录。`
                                : `重新启用客服「${op.displayName}」？`
                            )
                          ) {
                            toggleMut.mutate(op);
                          }
                        }}
                        disabled={toggleMut.isPending}
                      >
                        {op.isActive ? (
                          <>
                            <Pause className="h-3.5 w-3.5" />
                            停用
                          </>
                        ) : (
                          <>
                            <Play className="h-3.5 w-3.5" />
                            启用
                          </>
                        )}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {operators.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                    暂无客服，点击右上角「+ 新建客服」开始
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ----- 当前账号领取状态 ----- */}
      <ClaimsPanel operators={operators} accounts={accounts} />

      {showCreate ? <CreateOperatorModal onClose={() => setShowCreate(false)} /> : null}
      {rebindTarget ? (
        <RebindTotpModal operator={rebindTarget} onClose={() => setRebindTarget(null)} />
      ) : null}
    </div>
  );
}
