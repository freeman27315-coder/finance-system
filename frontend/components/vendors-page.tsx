"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Building2,
  CheckCircle2,
  Plus,
  RefreshCcw
} from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createVendor,
  createVendorBill,
  getVendorBills,
  getVendorSummary,
  getVendors,
  settleVendorBill
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { BillDirection, Vendor, VendorBill } from "@/types";

function formatDueDate(value: string | null) {
  if (!value) return "-";
  return value.length >= 10 ? value.slice(0, 10) : value;
}

function VendorSummaryCards() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["vendor-summary"],
    queryFn: getVendorSummary
  });

  const payable = data?.payableMinor ?? 0;
  const receivable = data?.receivableMinor ?? 0;
  const net = data?.netMinor ?? 0;
  const currency = data?.currency ?? "CNY";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新汇总
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">应付总额</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold text-red-600">
                {formatMoney(payable, currency)}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-red-50 text-red-600">
              <ArrowUpRight className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">应收总额</div>
              <div className="mt-1 tabular-nums text-2xl font-semibold text-green-600">
                {formatMoney(receivable, currency)}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
              <ArrowDownLeft className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm text-muted-foreground">净额</div>
              <div
                className={cn(
                  "mt-1 tabular-nums text-2xl font-semibold",
                  net >= 0 ? "text-green-600" : "text-red-600"
                )}
              >
                {formatMoney(net, currency)}
              </div>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
              <Building2 className="h-5 w-5" aria-hidden="true" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CreateVendorModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) {
        throw new Error("供应商名称不能为空");
      }
      return createVendor({
        name: name.trim(),
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["vendors"] });
      await queryClient.invalidateQueries({ queryKey: ["vendor-summary"] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>新增供应商</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">供应商名称</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="供应商名称"
              autoFocus
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
              {mutation.isPending ? "创建中..." : "创建"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateBillModal({ vendor, onClose }: { vendor: Vendor; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [direction, setDirection] = useState<BillDirection>("payable");
  const [amount, setAmount] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [remark, setRemark] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      return createVendorBill(vendor.id, {
        direction,
        amount,
        dueDate: dueDate || undefined,
        remark: remark.trim() === "" ? undefined : remark.trim()
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["vendor-bills", vendor.id] });
      await queryClient.invalidateQueries({ queryKey: ["vendor-summary"] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>新增账单 · {vendor.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">方向</div>
            <div className="grid grid-cols-2 rounded-md border border-border p-1">
              {(["payable", "receivable"] as BillDirection[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={cn(
                    "flex h-8 items-center justify-center gap-2 rounded text-sm font-medium text-muted-foreground",
                    direction === item && "bg-muted text-foreground"
                  )}
                  onClick={() => setDirection(item)}
                >
                  {item === "payable" ? (
                    <ArrowUpRight className="h-4 w-4 text-red-600" aria-hidden="true" />
                  ) : (
                    <ArrowDownLeft className="h-4 w-4 text-green-600" aria-hidden="true" />
                  )}
                  {item === "payable" ? "应付" : "应收"}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">金额</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="金额"
              type="number"
              min="0"
              step="0.01"
            />
          </div>
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">到期日（选填）</div>
            <input
              className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
              type="date"
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
              {mutation.isPending ? "创建中..." : "创建"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function VendorList({
  vendors,
  selectedVendorId,
  onSelect,
  onCreate
}: {
  vendors: Vendor[];
  selectedVendorId: string;
  onSelect: (vendorId: string) => void;
  onCreate: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>供应商</CardTitle>
          <Button size="sm" onClick={onCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新增供应商
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {vendors.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            暂无供应商，点击右上角「新增供应商」开始
          </div>
        ) : (
          vendors.map((vendor) => (
            <button
              key={vendor.id}
              type="button"
              className={cn(
                "w-full rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:bg-muted/60",
                selectedVendorId === vendor.id && "bg-muted"
              )}
              onClick={() => onSelect(vendor.id)}
            >
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <span className="font-medium">{vendor.name}</span>
              </div>
              {vendor.remark ? (
                <div className="mt-1 text-xs text-muted-foreground">{vendor.remark}</div>
              ) : null}
            </button>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function BillTable({
  vendor,
  bills,
  onCreate
}: {
  vendor: Vendor | null;
  bills: VendorBill[];
  onCreate: () => void;
}) {
  const queryClient = useQueryClient();
  const [errorBillId, setErrorBillId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const settleMutation = useMutation({
    mutationFn: settleVendorBill,
    onSuccess: async () => {
      setErrorBillId(null);
      setErrorMessage(null);
      if (vendor) {
        await queryClient.invalidateQueries({ queryKey: ["vendor-bills", vendor.id] });
      }
      await queryClient.invalidateQueries({ queryKey: ["vendor-summary"] });
    },
    onError: (err, billId) => {
      setErrorBillId(billId);
      setErrorMessage(err instanceof Error ? err.message : "操作失败");
    }
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{vendor ? `${vendor.name} 的账单` : "账单"}</CardTitle>
          <Button size="sm" onClick={onCreate} disabled={!vendor}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            新增账单
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {errorMessage ? (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600">
            {errorMessage}
          </div>
        ) : null}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>方向</TableHead>
              <TableHead className="text-right">金额</TableHead>
              <TableHead>到期日</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bills.map((bill) => {
              const isPayable = bill.direction === "payable";
              const isPending = bill.status === "pending";
              return (
                <TableRow key={bill.id}>
                  <TableCell>
                    <Badge tone={isPayable ? "danger" : "success"}>
                      {isPayable ? "应付" : "应收"}
                    </Badge>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums font-semibold",
                      isPayable ? "text-red-600" : "text-green-600"
                    )}
                  >
                    {formatMoney(bill.amountMinor, bill.currency)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDueDate(bill.dueDate)}</TableCell>
                  <TableCell>
                    <Badge tone={isPending ? "neutral" : "success"}>
                      {isPending ? "待结清" : "已结清"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{bill.remark ?? "-"}</TableCell>
                  <TableCell className="text-right">
                    {isPending ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => settleMutation.mutate(bill.id)}
                        disabled={settleMutation.isPending && errorBillId !== bill.id}
                      >
                        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                        标记结清
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">已结清</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {bills.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  {vendor ? "该供应商暂无账单" : "请先在左侧选中或新增供应商"}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function VendorsPage() {
  const [selectedVendorId, setSelectedVendorId] = useState("");
  const [showCreateVendor, setShowCreateVendor] = useState(false);
  const [showCreateBill, setShowCreateBill] = useState(false);

  const { data: vendors = [], isFetching, refetch } = useQuery({
    queryKey: ["vendors"],
    queryFn: getVendors
  });

  useEffect(() => {
    if (vendors.length === 0) {
      if (selectedVendorId !== "") {
        setSelectedVendorId("");
      }
      return;
    }
    if (!vendors.find((vendor) => vendor.id === selectedVendorId)) {
      setSelectedVendorId(vendors[0].id);
    }
  }, [vendors, selectedVendorId]);

  const selectedVendor = vendors.find((vendor) => vendor.id === selectedVendorId) ?? null;

  const { data: bills = [] } = useQuery({
    queryKey: ["vendor-bills", selectedVendor?.id ?? ""],
    queryFn: () => (selectedVendor ? getVendorBills(selectedVendor.id) : Promise.resolve([])),
    enabled: Boolean(selectedVendor)
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">供应商账单</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            管理供应商应付/应收账单，标记结清后自动刷新汇总。
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          刷新供应商
        </Button>
      </div>

      <VendorSummaryCards />

      <div className="grid gap-3 lg:grid-cols-[0.9fr_1.6fr]">
        <VendorList
          vendors={vendors}
          selectedVendorId={selectedVendor?.id ?? ""}
          onSelect={setSelectedVendorId}
          onCreate={() => setShowCreateVendor(true)}
        />
        <BillTable
          vendor={selectedVendor}
          bills={bills}
          onCreate={() => setShowCreateBill(true)}
        />
      </div>

      {showCreateVendor ? (
        <CreateVendorModal onClose={() => setShowCreateVendor(false)} />
      ) : null}
      {showCreateBill && selectedVendor ? (
        <CreateBillModal vendor={selectedVendor} onClose={() => setShowCreateBill(false)} />
      ) : null}
    </div>
  );
}
