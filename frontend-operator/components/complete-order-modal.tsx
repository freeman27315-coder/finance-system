"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { completeOrder, getSalesWalletOptions } from "@/lib/api";
import { formatDateTimeSeconds, stripTrailingZeros } from "@/lib/utils";
import type { OperatorOrder, SaleCurrency } from "@/types";

// CEO 2026-05-20 #134: 先选渠道(淘宝/台湾) → 自动锁币种 → 再选具体钱包。
// 渠道与币种 1:1 映射: TAOBAO=CNY, TAIWAN=TWD。

const CHANNEL_TO_CURRENCY: Record<string, SaleCurrency> = {
  TAOBAO: "CNY",
  TAIWAN: "TWD"
};

export function CompleteOrderModal({
  order,
  operatorId,
  operatorDisplayName,
  onClose
}: {
  order: OperatorOrder;
  operatorId: number;
  operatorDisplayName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [productName, setProductName] = useState(order.productName ?? "");
  const [salePrice, setSalePrice] = useState(
    stripTrailingZeros(order.salePrice)
  );
  const [channelCode, setChannelCode] = useState<string>("");
  const [walletPoolId, setWalletPoolId] = useState<number | "">("");
  const [remark, setRemark] = useState(order.remark ?? "");
  const [error, setError] = useState<string | null>(null);

  const walletsQuery = useQuery({
    queryKey: ["sales-wallet-options"],
    queryFn: getSalesWalletOptions
  });

  const groups = walletsQuery.data ?? [];
  const selectedGroup = groups.find((g) => g.groupCode === channelCode);
  const wallets = selectedGroup?.wallets ?? [];
  const selectedWallet = wallets.find((w) => w.id === walletPoolId);

  // 选完渠道后, 币种由渠道决定 (TAOBAO=CNY, TAIWAN=TWD)
  const saleCurrency: SaleCurrency | null = channelCode
    ? CHANNEL_TO_CURRENCY[channelCode] ?? null
    : null;

  const mutation = useMutation({
    mutationFn: async () => {
      if (!productName.trim()) throw new Error("商品名不能为空");
      if (!salePrice.trim()) throw new Error("售价不能为空");
      if (!channelCode) throw new Error("请选渠道(淘宝/台湾)");
      if (typeof walletPoolId !== "number") throw new Error("请选具体钱包");
      if (!selectedWallet) throw new Error("钱包未找到");
      if (!saleCurrency) throw new Error("币种未确定");
      return completeOrder(order.id, {
        operatorId,
        productName: productName.trim(),
        salePrice: salePrice.trim(),
        saleCurrency,
        walletPoolId,
        walletItemLabel: selectedWallet.name,
        remark: remark.trim() || undefined
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-orders"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "提交失败")
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>补销售信息 · {order.orderNo}</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              本币 {stripTrailingZeros(order.amountLocal)} {order.currencyLocal} · 订单时间{" "}
              {formatDateTimeSeconds(order.orderAt)}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 销售日期 + 经办人 — 系统自动,只读 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                销售日期(系统自动)
              </label>
              <div className="flex h-10 items-center rounded-md border border-border bg-muted px-3 text-xs tabular-nums text-muted-foreground">
                {formatDateTimeSeconds(order.saleDate ?? order.orderAt)}
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                经办人(自动 = 登录客服)
              </label>
              <div className="flex h-10 items-center rounded-md border border-border bg-muted px-3 text-sm text-muted-foreground">
                {operatorDisplayName}
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              商品名 <span className="text-red-600">*</span>
            </label>
            <Input
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder="例: 5350 档"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1 col-span-2">
              <label className="text-xs font-medium">
                售价 <span className="text-red-600">*</span>
              </label>
              <Input
                inputMode="decimal"
                value={salePrice}
                onChange={(e) => setSalePrice(e.target.value)}
                placeholder="如 5350.00"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                币种(渠道锁定)
              </label>
              <div
                className="flex h-10 items-center justify-center rounded-md border border-border bg-muted px-3 text-sm font-semibold tracking-wide"
                title={saleCurrency ? `渠道${selectedGroup?.groupLabel}锁定: ${saleCurrency}` : "先选渠道"}
              >
                {saleCurrency ?? <span className="text-xs text-muted-foreground/60">先选渠道</span>}
              </div>
            </div>
          </div>

          {/* 渠道选择 */}
          <div className="space-y-1">
            <label className="text-xs font-medium">
              渠道 <span className="text-red-600">*</span>
            </label>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={channelCode}
              onChange={(e) => {
                setChannelCode(e.target.value);
                setWalletPoolId(""); // 换渠道清空钱包
              }}
              disabled={walletsQuery.isLoading}
            >
              <option value="">{walletsQuery.isLoading ? "加载中…" : "请选渠道"}</option>
              {groups.map((g) => (
                <option key={g.groupCode} value={g.groupCode}>
                  {g.groupLabel} ({CHANNEL_TO_CURRENCY[g.groupCode] ?? g.wallets[0]?.currency})
                </option>
              ))}
            </select>
          </div>

          {/* 具体钱包 */}
          <div className="space-y-1">
            <label className="text-xs font-medium">
              收款钱包 <span className="text-red-600">*</span>
            </label>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletPoolId}
              onChange={(e) =>
                setWalletPoolId(e.target.value === "" ? "" : Number(e.target.value))
              }
              disabled={!channelCode}
            >
              <option value="">
                {channelCode ? "请选钱包" : "先选渠道"}
              </option>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              备注(可自由填写)
            </label>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder="如: 客户加急 / 续费 / 特殊情况备忘"
            />
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>
              取消
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setError(null);
                mutation.mutate();
              }}
              disabled={mutation.isPending}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              {mutation.isPending ? "提交中…" : "提交销售信息"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
