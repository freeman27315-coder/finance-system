"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  Banknote,
  CheckCircle2,
  FileSpreadsheet,
  ListOrdered,
  Loader2,
  RefreshCcw,
  Snowflake,
  Wallet,
  X
} from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getTaobaoShops,
  getTaobaoWalletTransactions,
  importTaobaoExcel,
  releaseAggregator,
  transferTaobaoToStoreAlipay,
  withdrawTaobao
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type {
  TaobaoImportReport,
  TaobaoReleaseReport,
  TaobaoShop,
  TaobaoShopWallet
} from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.length >= 16 ? value.slice(0, 16).replace("T", " ") : value;
}

type WalletRowKind =
  | "unconfirmed-alipay"
  | "unconfirmed-wechat"
  | "aggregator-frozen"
  | "aggregator-available"
  | "bank-card";

type WalletRowDef = {
  kind: WalletRowKind;
  label: string;
  wallet: TaobaoShopWallet;
  icon: React.ReactNode;
  tone: "neutral" | "frozen" | "available" | "bank";
};

function getWalletRows(shop: TaobaoShop): WalletRowDef[] {
  return [
    {
      kind: "unconfirmed-alipay",
      label: "支付宝支付在途",
      wallet: shop.unconfirmedAlipay,
      icon: <Wallet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />,
      tone: "neutral"
    },
    {
      kind: "unconfirmed-wechat",
      label: "微信支付在途",
      wallet: shop.unconfirmedWechat,
      icon: <Wallet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />,
      tone: "neutral"
    },
    {
      kind: "aggregator-frozen",
      label: "聚合支付·冻结中",
      wallet: shop.aggregatorFrozen,
      icon: <Snowflake className="h-4 w-4 text-blue-600" aria-hidden="true" />,
      tone: "frozen"
    },
    {
      kind: "aggregator-available",
      label: "聚合支付·可提现",
      wallet: shop.aggregatorAvailable,
      icon: <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />,
      tone: "available"
    },
    {
      kind: "bank-card",
      label: "银行卡",
      wallet: shop.bankCard,
      icon: <Banknote className="h-4 w-4 text-amber-600" aria-hidden="true" />,
      tone: "bank"
    }
  ];
}

// ---------------------------------------------------------------------------
// 流水抽屉
// ---------------------------------------------------------------------------

function TransactionsModal({
  shop,
  wallet,
  walletLabel,
  onClose
}: {
  shop: TaobaoShop;
  wallet: TaobaoShopWallet;
  walletLabel: string;
  onClose: () => void;
}) {
  const { data: transactions = [], isFetching } = useQuery({
    queryKey: ["taobao-wallet-transactions", shop.id, wallet.id],
    queryFn: () => getTaobaoWalletTransactions(shop.id, wallet.id)
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[80vh] w-full max-w-3xl flex-col">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>
              {shop.name} · {walletLabel} · 流水
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" aria-hidden="true" />
              关闭
            </Button>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            当前余额 <span className="tabular-nums">{formatMoney(wallet.balanceMinor, "CNY")}</span>
          </div>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto">
          {transactions.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
              {isFetching ? "加载中..." : "暂无流水"}
            </div>
          ) : (
            <div className="divide-y divide-border rounded-md border border-border">
              {transactions.map((tx) => {
                const isIn = tx.direction === "in";
                return (
                  <div key={tx.id} className="flex items-start justify-between gap-3 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge tone={isIn ? "success" : "danger"}>{isIn ? "入账" : "出账"}</Badge>
                        <span
                          className={cn(
                            "tabular-nums font-semibold",
                            isIn ? "text-green-600" : "text-red-600"
                          )}
                        >
                          {isIn ? "+" : "-"}
                          {formatMoney(tx.amountMinor, "CNY")}
                        </span>
                        {tx.matureAt ? (
                          <Badge tone="transfer">到期 {formatDateTime(tx.matureAt)}</Badge>
                        ) : null}
                      </div>
                      {tx.remark ? (
                        <div className="mt-1 truncate text-xs text-muted-foreground">{tx.remark}</div>
                      ) : null}
                    </div>
                    <div className="shrink-0 text-xs text-muted-foreground">
                      {formatDateTime(tx.createdAt)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 提现弹窗（可提现 → 银行卡）
// ---------------------------------------------------------------------------

function WithdrawModal({ shop, onClose }: { shop: TaobaoShop; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const numAmount = Number.parseFloat(amount);
      if (!amount || Number.isNaN(numAmount) || numAmount <= 0) {
        throw new Error("金额必须大于 0");
      }
      return withdrawTaobao(shop.id, {
        amount,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taobao-shops"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-wallet-transactions", shop.id] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "提现失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>提现到银行卡 · {shop.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
            <div className="text-xs text-muted-foreground">可提现余额</div>
            <div className="mt-1 tabular-nums text-base font-semibold text-emerald-600">
              {formatMoney(shop.aggregatorAvailable.balanceMinor, "CNY")}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">金额（CNY）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="提现金额"
              type="number"
              min="0"
              step="0.01"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填）</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
              placeholder="备注，默认为「提现到银行卡」"
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
              {mutation.isPending ? "提交中..." : "确认提现"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 转店铺支付宝（3 店铺都可调；兔仔为账面记账，成功后 inline 提示"已记账"）
// ---------------------------------------------------------------------------

function TransferToStoreAlipayModal({
  shop,
  onClose,
  onBookkeepingSuccess
}: {
  shop: TaobaoShop;
  onClose: () => void;
  onBookkeepingSuccess: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isBookkeeping = shop.storeAlipayWallet.type === "TAOBAO";

  const mutation = useMutation({
    mutationFn: async () => {
      let amountValue: string | undefined;
      if (amount.trim() !== "") {
        const num = Number.parseFloat(amount);
        if (Number.isNaN(num) || num <= 0) {
          throw new Error("金额必须大于 0");
        }
        amountValue = amount;
      }
      return transferTaobaoToStoreAlipay(shop.id, {
        amount: amountValue,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["taobao-shops"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-wallet-transactions", shop.id] });
      await queryClient.invalidateQueries({ queryKey: ["asset-wallets"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      if (isBookkeeping) {
        onBookkeepingSuccess(`${shop.name}：已记账（实际钱不在手中）`);
      }
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "转账失败");
    }
  });

  const targetName = shop.storeAlipayWallet.name;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>
            转账到 {targetName} · {shop.name}
          </CardTitle>
          {isBookkeeping ? (
            <div className="mt-2 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
              <Badge tone="warning">账面记账</Badge>
              <span>本店铺为兔仔，转账仅做账面记录，实际钱不在我手。</span>
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
            <div className="text-xs text-muted-foreground">银行卡余额</div>
            <div className="mt-1 tabular-nums text-base font-semibold text-amber-600">
              {formatMoney(shop.bankCard.balanceMinor, "CNY")}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">金额（CNY，留空 = 全部余额）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="留空 = 全部银行卡余额"
              type="number"
              min="0"
              step="0.01"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">备注（选填）</div>
            <textarea
              className="min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={remark}
              onChange={(event) => setRemark(event.target.value)}
              placeholder="备注，默认为「提现」"
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
              {mutation.isPending ? "提交中..." : "确认转账"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 导入 Excel
// ---------------------------------------------------------------------------

function ImportExcelModal({ shop, onClose }: { shop: TaobaoShop; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<TaobaoImportReport | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) {
        throw new Error("请选择 .xlsx 文件");
      }
      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        throw new Error("仅支持 .xlsx 文件");
      }
      return importTaobaoExcel(shop.id, file);
    },
    onSuccess: async (result) => {
      setReport(result);
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["taobao-shops"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-wallet-transactions", shop.id] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "导入失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="flex max-h-[85vh] w-full max-w-lg flex-col">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>导入今日千牛 Excel · {shop.name}</CardTitle>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" aria-hidden="true" />
              关闭
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex-1 space-y-3 overflow-y-auto">
          {report ? (
            <div className="space-y-2">
              <div className="rounded-md border border-emerald-500/40 bg-emerald-50/60 p-3 text-sm text-emerald-700">
                导入完成 · {report.shopName}
              </div>
              <div className="divide-y divide-border rounded-md border border-border text-sm">
                <ReportRow label="总解析行数" value={report.totalRowsParsed} />
                <ReportRow label="新建订单" value={report.createdOrders} highlight={report.createdOrders > 0} />
                <ReportRow
                  label="状态变化订单"
                  value={report.statusChangedOrders}
                  highlight={report.statusChangedOrders > 0}
                />
                <ReportRow label="撤销关闭" value={report.closedReverted} />
                <ReportRow label="跳过（无变化）" value={report.skippedNoChange} />
                <ReportRow label="跳过（未付款/未发货）" value={report.skippedUnpaidOrUnshipped} />
                <ReportRow label="跳过（未知支付方式）" value={report.skippedUnknownPayment} />
              </div>
              {report.errors.length > 0 ? (
                <div className="space-y-1 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm">
                  <div className="font-medium text-red-700">错误 {report.errors.length} 条</div>
                  <ul className="list-inside list-disc space-y-1 text-xs text-red-700">
                    {report.errors.map((msg, idx) => (
                      <li key={idx}>{msg}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <>
              <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                上传千牛后台导出的 .xlsx 文件，按规则入账每条订单并对老订单做 reconcile。
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">选择 Excel 文件</div>
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={(event) => {
                    const f = event.target.files?.[0] ?? null;
                    setFile(f);
                    setError(null);
                  }}
                  className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
                />
                {file ? (
                  <div className="text-xs text-muted-foreground">
                    已选：{file.name}（{Math.round(file.size / 1024)} KB）
                  </div>
                ) : null}
              </div>
              {error ? (
                <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
                  {error}
                </div>
              ) : null}
            </>
          )}
        </CardContent>
        <div className="flex justify-end gap-2 border-t border-border px-6 py-3">
          {report ? (
            <Button onClick={onClose}>完成</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
                取消
              </Button>
              <Button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending || !file}
              >
                {mutation.isPending ? "导入中..." : "开始导入"}
              </Button>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}

function ReportRow({
  label,
  value,
  highlight
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "tabular-nums font-semibold",
          highlight ? "text-emerald-600" : "text-foreground"
        )}
      >
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 钱包行
// ---------------------------------------------------------------------------

function WalletRow({
  row,
  onShowTransactions,
  onWithdraw,
  onTransferToStoreAlipay,
  releasing,
  releaseReport,
  onRelease
}: {
  row: WalletRowDef;
  onShowTransactions: (wallet: TaobaoShopWallet, label: string) => void;
  onWithdraw: () => void;
  onTransferToStoreAlipay: () => void;
  releasing: boolean;
  releaseReport: TaobaoReleaseReport | null;
  onRelease: () => void;
}) {
  const isBankCard = row.kind === "bank-card";
  const isFrozen = row.kind === "aggregator-frozen";
  const isAvailable = row.kind === "aggregator-available";

  const balanceColor =
    row.tone === "available"
      ? "text-emerald-600"
      : row.tone === "frozen"
        ? "text-blue-600"
        : row.tone === "bank"
          ? "text-amber-700"
          : "text-foreground";

  return (
    <div className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        {row.icon}
        <div className="text-sm font-medium">{row.label}</div>
      </div>
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <div className={cn("tabular-nums text-base font-semibold", balanceColor)}>
          {formatMoney(row.wallet.balanceMinor, "CNY")}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {isFrozen ? (
            <Button
              variant="outline"
              size="sm"
              onClick={onRelease}
              disabled={releasing}
              className={cn(
                releaseReport && releaseReport.maturedCount > 0
                  ? "border-emerald-500/50 bg-emerald-50/60 text-emerald-700"
                  : ""
              )}
              title="一键解冻所有到期"
            >
              {releasing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Snowflake className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              一键解冻到期
            </Button>
          ) : null}
          {isAvailable ? (
            <Button variant="outline" size="sm" onClick={onWithdraw}>
              <ArrowRightLeft className="h-3.5 w-3.5" aria-hidden="true" />
              提现
            </Button>
          ) : null}
          {isBankCard ? (
            <Button variant="outline" size="sm" onClick={onTransferToStoreAlipay}>
              <ArrowRightLeft className="h-3.5 w-3.5" aria-hidden="true" />
              转店铺支付宝
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onShowTransactions(row.wallet, row.label)}
          >
            <ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />
            流水
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 店铺卡片
// ---------------------------------------------------------------------------

function ShopCard({
  shop,
  onShowTransactions,
  onWithdraw,
  onTransferToStoreAlipay,
  onImport
}: {
  shop: TaobaoShop;
  onShowTransactions: (wallet: TaobaoShopWallet, label: string) => void;
  onWithdraw: () => void;
  onTransferToStoreAlipay: () => void;
  onImport: () => void;
}) {
  const queryClient = useQueryClient();
  const [releaseReport, setReleaseReport] = useState<TaobaoReleaseReport | null>(null);
  const [releaseError, setReleaseError] = useState<string | null>(null);

  const releaseMutation = useMutation({
    mutationFn: () => releaseAggregator(shop.id),
    onSuccess: async (report) => {
      setReleaseReport(report);
      setReleaseError(null);
      await queryClient.invalidateQueries({ queryKey: ["taobao-shops"] });
      await queryClient.invalidateQueries({ queryKey: ["taobao-wallet-transactions", shop.id] });
    },
    onError: (err) => {
      setReleaseError(err instanceof Error ? err.message : "解冻失败");
      setReleaseReport(null);
    }
  });

  const rows = getWalletRows(shop);
  const isBookkeeping = shop.storeAlipayWallet.type === "TAOBAO";

  return (
    <Card className="border">
      <CardHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-lg">{shop.name}</CardTitle>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span>店铺支付宝：{shop.storeAlipayWallet.name}</span>
              {isBookkeeping ? <Badge tone="warning">账面</Badge> : null}
            </div>
            {shop.remark ? (
              <div className="mt-1 text-xs text-muted-foreground">{shop.remark}</div>
            ) : null}
          </div>
          <Button variant="outline" size="sm" onClick={onImport}>
            <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
            导入今日千牛 Excel
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className={cn(
            "flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between",
            isBookkeeping
              ? "border-amber-200 bg-amber-50/60"
              : "border-emerald-200 bg-emerald-50/60"
          )}
        >
          <div className="flex items-center gap-2">
            <Wallet
              className={cn(
                "h-4 w-4",
                isBookkeeping ? "text-amber-700" : "text-emerald-700"
              )}
              aria-hidden="true"
            />
            <div>
              <div className="flex items-center gap-1.5 text-sm font-medium">
                <span>店铺支付宝</span>
                {isBookkeeping ? <Badge tone="warning">账面记账</Badge> : null}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                {shop.storeAlipayWallet.name}
                {isBookkeeping ? "（钱不在我手）" : ""}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 sm:justify-end">
            <div
              className={cn(
                "tabular-nums text-xl font-bold",
                isBookkeeping ? "text-amber-700" : "text-emerald-700"
              )}
            >
              {formatMoney(shop.storeAlipayWallet.balanceMinor, "CNY")}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                onShowTransactions(shop.storeAlipayWallet, "店铺支付宝")
              }
            >
              <ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />
              流水
            </Button>
          </div>
        </div>
        <div className="divide-y divide-border rounded-md border border-border">
          {rows.map((row) => (
            <WalletRow
              key={row.kind}
              row={row}
              onShowTransactions={onShowTransactions}
              onWithdraw={onWithdraw}
              onTransferToStoreAlipay={onTransferToStoreAlipay}
              releasing={releaseMutation.isPending}
              releaseReport={releaseReport}
              onRelease={() => releaseMutation.mutate()}
            />
          ))}
        </div>
        {releaseError ? (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
            解冻失败：{releaseError}
          </div>
        ) : null}
        {releaseReport ? (
          <div className="rounded-md border border-emerald-500/40 bg-emerald-50/60 p-3 text-sm">
            <div className="flex items-center gap-2 font-medium text-emerald-700">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {releaseReport.maturedCount > 0
                ? `已解冻 ${releaseReport.maturedCount} 笔到期`
                : "暂无到期可解冻"}
            </div>
            <div className="mt-1 grid grid-cols-2 gap-2 text-xs text-emerald-700/90">
              <div>
                累计解冻
                <span className="ml-1 tabular-nums font-semibold">
                  {formatMoney(releaseReport.maturedAmountMinor, "CNY")}
                </span>
              </div>
              <div>
                冻结余额
                <span className="ml-1 tabular-nums font-semibold">
                  {formatMoney(releaseReport.frozenBalanceAfterMinor, "CNY")}
                </span>
              </div>
              <div className="col-span-2">
                可提现余额
                <span className="ml-1 tabular-nums font-semibold">
                  {formatMoney(releaseReport.availableBalanceAfterMinor, "CNY")}
                </span>
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 主页
// ---------------------------------------------------------------------------

export function TaobaoPage() {
  const { data: shops = [], isFetching, refetch } = useQuery({
    queryKey: ["taobao-shops"],
    queryFn: getTaobaoShops
  });

  const [withdrawShop, setWithdrawShop] = useState<TaobaoShop | null>(null);
  const [transferShop, setTransferShop] = useState<TaobaoShop | null>(null);
  const [importShop, setImportShop] = useState<TaobaoShop | null>(null);
  const [transactionsTarget, setTransactionsTarget] = useState<{
    shop: TaobaoShop;
    wallet: TaobaoShopWallet;
    label: string;
  } | null>(null);
  const [bookkeepingToast, setBookkeepingToast] = useState<string | null>(null);

  // 兔仔账面记账成功 toast：4 秒自动消失
  useEffect(() => {
    if (bookkeepingToast === null) return;
    const timer = window.setTimeout(() => setBookkeepingToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [bookkeepingToast]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">淘宝店铺</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            3 店铺 × 5 钱包：支付宝支付在途 / 微信支付在途 / 聚合冻结 / 聚合可提现 / 银行卡。导入千牛
            Excel 自动入账，T+7 解冻；银行卡余额可转入店铺支付宝（兔仔为账面记账）。
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className={cn("h-4 w-4", isFetching && "animate-spin")} aria-hidden="true" />
          刷新
        </Button>
      </div>

      {shops.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            {isFetching ? "加载中..." : "暂无淘宝店铺"}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {shops.map((shop) => (
            <ShopCard
              key={shop.id}
              shop={shop}
              onShowTransactions={(wallet, label) =>
                setTransactionsTarget({ shop, wallet, label })
              }
              onWithdraw={() => setWithdrawShop(shop)}
              onTransferToStoreAlipay={() => setTransferShop(shop)}
              onImport={() => setImportShop(shop)}
            />
          ))}
        </div>
      )}

      {withdrawShop ? (
        <WithdrawModal shop={withdrawShop} onClose={() => setWithdrawShop(null)} />
      ) : null}
      {transferShop ? (
        <TransferToStoreAlipayModal
          shop={transferShop}
          onClose={() => setTransferShop(null)}
          onBookkeepingSuccess={(message) => setBookkeepingToast(message)}
        />
      ) : null}
      {importShop ? (
        <ImportExcelModal shop={importShop} onClose={() => setImportShop(null)} />
      ) : null}
      {transactionsTarget ? (
        <TransactionsModal
          shop={transactionsTarget.shop}
          wallet={transactionsTarget.wallet}
          walletLabel={transactionsTarget.label}
          onClose={() => setTransactionsTarget(null)}
        />
      ) : null}

      {bookkeepingToast ? (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 shadow-lg"
        >
          <Badge tone="warning">账面</Badge>
          <div>{bookkeepingToast}</div>
          <button
            onClick={() => setBookkeepingToast(null)}
            className="ml-2 text-amber-700/70 hover:text-amber-900"
            aria-label="关闭提示"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
