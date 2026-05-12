"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { completeOrder, getWalletMethods } from "@/lib/api";
import { formatDateTimeSeconds } from "@/lib/utils";
import type { OperatorOrder, SaleCurrency } from "@/types";

const SALE_CURRENCIES: SaleCurrency[] = ["CNY", "USD", "USDT", "TWD"];

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
  const [salePrice, setSalePrice] = useState(order.salePrice ?? "");
  const [saleCurrency, setSaleCurrency] = useState<SaleCurrency>(
    (order.saleCurrency as SaleCurrency) ?? "CNY"
  );
  const [walletMethodId, setWalletMethodId] = useState<number | "">(
    order.walletMethodId ?? ""
  );
  const [walletItemId, setWalletItemId] = useState<number | "">(
    order.walletItemId ?? ""
  );
  const [error, setError] = useState<string | null>(null);

  const methodsQuery = useQuery({
    queryKey: ["wallet-methods"],
    queryFn: getWalletMethods
  });

  const methods = methodsQuery.data ?? [];
  const selectedMethod = methods.find((m) => m.id === walletMethodId);
  const items = selectedMethod?.items ?? [];

  // 切方式时清空旧的 item
  useEffect(() => {
    if (selectedMethod && walletItemId !== "") {
      const stillValid = items.some((it) => it.id === walletItemId);
      if (!stillValid) setWalletItemId("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walletMethodId]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!productName.trim()) throw new Error("商品名不能为空");
      if (!salePrice.trim()) throw new Error("售价不能为空");
      if (typeof walletMethodId !== "number") throw new Error("请选收款方式");
      if (typeof walletItemId !== "number") throw new Error("请选备注模板");
      return completeOrder(order.id, {
        operatorId,
        productName: productName.trim(),
        salePrice: salePrice.trim(),
        saleCurrency,
        walletMethodId,
        walletItemId
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-orders", order.accountId] });
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
              本币 {order.amountLocal} {order.currencyLocal} · 订单时间{" "}
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
                销售日期（系统自动，精确到秒）
              </label>
              <div className="flex h-10 items-center rounded-md border border-border bg-muted px-3 text-xs tabular-nums text-muted-foreground">
                {formatDateTimeSeconds(order.saleDate ?? order.orderAt)}
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                经办人（自动 = 登录客服）
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
              <label className="text-xs font-medium">
                币种 <span className="text-red-600">*</span>
              </label>
              <select
                className="h-10 w-full rounded-md border border-border bg-card px-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                value={saleCurrency}
                onChange={(e) => setSaleCurrency(e.target.value as SaleCurrency)}
              >
                {SALE_CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              收款方式 <span className="text-red-600">*</span>
            </label>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletMethodId}
              onChange={(e) =>
                setWalletMethodId(e.target.value === "" ? "" : Number(e.target.value))
              }
              disabled={methodsQuery.isLoading}
            >
              <option value="">{methodsQuery.isLoading ? "加载中…" : "请选择"}</option>
              {methods
                .filter((m) => m.isActive)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              备注模板 <span className="text-red-600">*</span>
            </label>
            <select
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={walletItemId}
              onChange={(e) =>
                setWalletItemId(e.target.value === "" ? "" : Number(e.target.value))
              }
              disabled={!selectedMethod}
            >
              <option value="">
                {selectedMethod ? "请选择" : "先选收款方式"}
              </option>
              {items
                .filter((it) => it.isActive)
                .map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.label}
                  </option>
                ))}
            </select>
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
