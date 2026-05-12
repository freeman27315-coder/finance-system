"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Gamepad2,
  Globe2,
  LogOut,
  PackageOpen,
  RefreshCcw,
  ShoppingBag,
  Undo2
} from "lucide-react";
import { useRouter } from "next/navigation";
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
  claimAccount,
  getAvailableAccounts,
  getMyClaims,
  returnClaim
} from "@/lib/api";
import { clearSession, type StoredOperator } from "@/lib/auth";
import { formatDateTimeSeconds } from "@/lib/utils";
import type { AvailableAccount, OperatorClaim } from "@/types";

const MAX_CLAIMS = 3;

export function OperatorDashboard({ operator }: { operator: StoredOperator }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const availQuery = useQuery({
    queryKey: ["operator-available-accounts"],
    queryFn: getAvailableAccounts
  });
  const claimsQuery = useQuery({
    queryKey: ["operator-my-claims", operator.id],
    queryFn: () => getMyClaims(operator.id)
  });

  const claimMut = useMutation({
    mutationFn: (accountId: number) => claimAccount(accountId, operator.id),
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["operator-available-accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-my-claims", operator.id] })
      ]);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "领取失败")
  });

  const returnMut = useMutation({
    mutationFn: (claimId: number) => returnClaim(claimId, operator.id),
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["operator-available-accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-my-claims", operator.id] })
      ]);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "归还失败")
  });

  const available = availQuery.data ?? [];
  const claims = (claimsQuery.data ?? []).filter((c) => c.isActive);
  const slotsLeft = Math.max(0, MAX_CLAIMS - claims.length);

  return (
    <div className="min-h-screen bg-background">
      {/* ----- Top bar ----- */}
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Gamepad2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold">XBOX 客服销售系统</div>
            <div className="text-xs text-muted-foreground">
              {operator.displayName} ({operator.loginName}) · 持有 {claims.length} / {MAX_CLAIMS}
            </div>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (claims.length > 0) {
              if (!confirm(`你还持有 ${claims.length} 个账号未归还，确定退出登录？退出后账号仍归你名下。`)) {
                return;
              }
            }
            clearSession();
            router.replace("/login");
          }}
        >
          <LogOut className="h-3.5 w-3.5" />
          退出登录
        </Button>
      </header>

      <main className="mx-auto w-full max-w-7xl space-y-5 px-6 py-5">
        {/* ----- 概览卡 ----- */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <PackageOpen className="h-3.5 w-3.5" />
                我持有的账号
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums">
                  {claims.length}
                </span>
                <span className="text-xs text-muted-foreground">/ {MAX_CLAIMS}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <ShoppingBag className="h-3.5 w-3.5" />
                可领账号池
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums text-emerald-700">
                  {available.length}
                </span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <CheckCircle2 className="h-3.5 w-3.5" />
                还能再领
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums">
                  {slotsLeft}
                </span>
                <span className="text-xs text-muted-foreground">个</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* ----- 我的领取 ----- */}
          <MyClaimsPanel
            claims={claims}
            onReturn={(claimId) => {
              setError(null);
              if (confirm("归还这个账号？归还后其他客服可以领取。")) {
                returnMut.mutate(claimId);
              }
            }}
            returnPending={returnMut.isPending}
            onRefresh={() => claimsQuery.refetch()}
            refreshing={claimsQuery.isFetching}
          />

          {/* ----- 可领账号池 ----- */}
          <AvailableAccountsPanel
            accounts={available}
            slotsLeft={slotsLeft}
            onClaim={(accountId) => {
              setError(null);
              if (slotsLeft <= 0) {
                setError(`你已持有 ${MAX_CLAIMS} 个账号(上限),请先归还后再领。`);
                return;
              }
              claimMut.mutate(accountId);
            }}
            claimPending={claimMut.isPending}
            onRefresh={() => availQuery.refetch()}
            refreshing={availQuery.isFetching}
          />
        </div>
      </main>
    </div>
  );
}

function MyClaimsPanel({
  claims,
  onReturn,
  returnPending,
  onRefresh,
  refreshing
}: {
  claims: OperatorClaim[];
  onReturn: (claimId: number) => void;
  returnPending: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>我领的账号</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            点账号进入详情(看密码 / 同步订单 / 补销售信息) — PR C 上线
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
          <RefreshCcw className="h-3.5 w-3.5" />
          刷新
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账号</TableHead>
              <TableHead>领取时间</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {claims.map((claim) => (
              <TableRow key={claim.id}>
                <TableCell className="text-sm">
                  <Badge tone="transfer">#{claim.accountId}</Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground tabular-nums">
                  {formatDateTimeSeconds(claim.claimedAt)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onReturn(claim.id)}
                    disabled={returnPending}
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                    归还
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {claims.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-xs text-muted-foreground">
                  你还没领账号，去右侧「可领账号池」挑一个
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function AvailableAccountsPanel({
  accounts,
  slotsLeft,
  onClaim,
  claimPending,
  onRefresh,
  refreshing
}: {
  accounts: AvailableAccount[];
  slotsLeft: number;
  onClaim: (accountId: number) => void;
  claimPending: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>可领账号池</CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            1 个账号同时只能被 1 个客服领取；你还能再领 {slotsLeft} 个
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
          <RefreshCcw className="h-3.5 w-3.5" />
          刷新
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账号编号</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>区域</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.map((account) => (
              <TableRow key={account.id}>
                <TableCell className="font-mono text-xs">
                  {account.accountNo ?? account.name}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  <span className="truncate block max-w-[160px]">
                    {account.loginEmail ?? "-"}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge tone={account.country === "UK" ? "danger" : "transfer"}>
                    <Globe2 className="mr-1 h-3 w-3" />
                    {account.country}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    onClick={() => onClaim(account.id)}
                    disabled={claimPending || slotsLeft <= 0}
                  >
                    领取
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {accounts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                  当前暂无可领账号，请联系 CEO 在后台标记账号为「可出库」
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
