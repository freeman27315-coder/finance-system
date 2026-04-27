"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CheckCircle2, Plus, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createVendor,
  createVendorBill,
  getDashboardData,
  getVendorBills,
  getVendors,
  settleVendorBill
} from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Vendor, VendorBill } from "@/types";

type BillDirection = "payable" | "receivable";

function Input({
  value,
  onChange,
  placeholder,
  type = "text"
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
}) {
  return (
    <input
      className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      type={type}
      min={type === "number" ? "0" : undefined}
      step={type === "number" ? "0.01" : undefined}
    />
  );
}

function VendorSummaryCards() {
  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardData
  });
  const summary = data?.vendorSummary;
  const items = [
    {
      label: "应收",
      value: summary?.receivableMinor ?? 0,
      tone: "success" as const,
      icon: ArrowDownLeft
    },
    {
      label: "应付",
      value: -(summary?.payableMinor ?? 0),
      tone: "danger" as const,
      icon: ArrowUpRight
    },
    {
      label: "净额",
      value: summary?.netMinor ?? 0,
      tone: "transfer" as const,
      icon: ArrowLeftRight
    }
  ];

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.label}>
            <CardContent className="flex items-center justify-between gap-4 p-5">
              <div>
                <div className="text-sm text-muted-foreground">{item.label}</div>
                <div className="mt-2 tabular-nums text-3xl font-semibold">
                  {formatMoney(item.value, "CNY", {
                    accounting: item.value < 0,
                    signed: item.value > 0
                  })}
                </div>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                <Icon className="h-5 w-5" />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function VendorCreateForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) {
        throw new Error("供应商名称不能为空");
      }
      return createVendor(name.trim(), remark.trim());
    },
    onSuccess: async () => {
      setName("");
      setRemark("");
      setMessage("供应商创建请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["vendors"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建失败")
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>新增供应商</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input value={name} onChange={setName} placeholder="供应商名称" />
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <Plus className="h-4 w-4" />
          创建供应商
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function VendorBillForm({ vendors, selectedVendorId }: { vendors: Vendor[]; selectedVendorId: string }) {
  const queryClient = useQueryClient();
  const [vendorId, setVendorId] = useState(selectedVendorId);
  const [direction, setDirection] = useState<BillDirection>("payable");
  const [amount, setAmount] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [remark, setRemark] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const activeVendorId = vendorId || selectedVendorId || vendors[0]?.id || "";

  const mutation = useMutation({
    mutationFn: () => {
      if (!activeVendorId) {
        throw new Error("请选择供应商");
      }
      if (!amount || Number(amount) <= 0) {
        throw new Error("金额必须大于 0");
      }
      return createVendorBill(activeVendorId, direction, amount, dueDate, remark);
    },
    onSuccess: async () => {
      setAmount("");
      setDueDate("");
      setRemark("");
      setMessage("账单创建请求已提交");
      await queryClient.invalidateQueries({ queryKey: ["vendor-bills"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建失败")
  });

  if (vendors.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>新增账单</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <select
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          value={activeVendorId}
          onChange={(event) => setVendorId(event.target.value)}
        >
          {vendors.map((vendor) => (
            <option key={vendor.id} value={vendor.id}>
              {vendor.name}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 rounded-md border border-border p-1">
          {(["payable", "receivable"] as BillDirection[]).map((item) => (
            <button
              key={item}
              className={cn(
                "h-8 rounded text-sm font-medium text-muted-foreground",
                direction === item && "bg-muted text-foreground"
              )}
              type="button"
              onClick={() => setDirection(item)}
            >
              {item === "payable" ? "应付" : "应收"}
            </button>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Input value={amount} onChange={setAmount} placeholder="金额" type="number" />
          <Input value={dueDate} onChange={setDueDate} placeholder="到期日" type="date" />
        </div>
        <Input value={remark} onChange={setRemark} placeholder="备注" />
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <Plus className="h-4 w-4" />
          创建账单
        </Button>
        {message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
      </CardContent>
    </Card>
  );
}

function VendorTable({
  vendors,
  selectedVendorId,
  onSelect
}: {
  vendors: Vendor[];
  selectedVendorId: string;
  onSelect: (vendorId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>供应商列表</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>供应商</TableHead>
              <TableHead>备注</TableHead>
              <TableHead>创建时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vendors.map((vendor) => (
              <TableRow
                key={vendor.id}
                className={cn("cursor-pointer", selectedVendorId === vendor.id && "bg-muted/70")}
                onClick={() => onSelect(vendor.id)}
              >
                <TableCell className="font-medium">{vendor.name}</TableCell>
                <TableCell className="text-muted-foreground">{vendor.remark || "-"}</TableCell>
                <TableCell className="text-muted-foreground">
                  {vendor.createdAt ? new Date(vendor.createdAt).toLocaleDateString("zh-CN") : "-"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function BillTable({ bills }: { bills: VendorBill[] }) {
  const queryClient = useQueryClient();
  const settleMutation = useMutation({
    mutationFn: settleVendorBill,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["vendor-bills"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>账单明细</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>供应商</TableHead>
              <TableHead>方向</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>到期日</TableHead>
              <TableHead>备注</TableHead>
              <TableHead className="text-right">金额</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bills.map((bill) => (
              <TableRow
                key={bill.id}
                className={bill.direction === "receivable" ? "border-l-2 border-l-emerald-500" : "border-l-2 border-l-red-500"}
              >
                <TableCell className="font-medium">{bill.vendorName}</TableCell>
                <TableCell>
                  <Badge tone={bill.direction === "receivable" ? "success" : "danger"}>
                    {bill.direction === "receivable" ? "应收" : "应付"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge tone={bill.status === "settled" ? "neutral" : "transfer"}>
                    {bill.status === "settled" ? "已结清" : "待处理"}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{bill.dueDate || "-"}</TableCell>
                <TableCell className="text-muted-foreground">{bill.remark || "-"}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">
                  {formatMoney(
                    bill.direction === "receivable" ? bill.amountMinor : -bill.amountMinor,
                    "CNY",
                    { accounting: bill.direction === "payable", signed: bill.direction === "receivable" }
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => settleMutation.mutate(bill.id)}
                    disabled={bill.status === "settled" || settleMutation.isPending}
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    结清
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {bills.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  当前供应商暂无账单
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
  const { data: vendors = [], isFetching, refetch } = useQuery({
    queryKey: ["vendors"],
    queryFn: getVendors
  });
  const selectedVendor = vendors.find((vendor) => vendor.id === selectedVendorId) ?? vendors[0];
  const { data: bills = [] } = useQuery({
    queryKey: ["vendor-bills", selectedVendor?.id],
    queryFn: () => getVendorBills(selectedVendor as Vendor),
    enabled: Boolean(selectedVendor)
  });
  const pendingBills = useMemo(() => bills.filter((bill) => bill.status === "pending"), [bills]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
        <div>
          <h2 className="text-2xl font-semibold tracking-normal">供应商往来</h2>
          <p className="mt-1 text-sm text-muted-foreground">供应商应付、应收、待处理账单和结清状态。</p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCcw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      <VendorSummaryCards />
      <div className="grid gap-3 xl:grid-cols-[0.8fr_1.2fr]">
        <VendorCreateForm />
        <VendorBillForm vendors={vendors} selectedVendorId={selectedVendor?.id ?? ""} />
      </div>
      <div className="grid gap-3 xl:grid-cols-[0.9fr_1.1fr]">
        <VendorTable vendors={vendors} selectedVendorId={selectedVendor?.id ?? ""} onSelect={setSelectedVendorId} />
        <Card>
          <CardContent className="p-5">
            <div className="text-sm text-muted-foreground">当前待处理账单</div>
            <div className="mt-2 tabular-nums text-3xl font-semibold">{pendingBills.length}</div>
          </CardContent>
        </Card>
      </div>
      <BillTable bills={bills} />
    </div>
  );
}
