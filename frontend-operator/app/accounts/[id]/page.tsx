"use client";

import { AccountDetail } from "@/components/account-detail";
import { useRequireAuth } from "@/lib/auth";
import { useParams } from "next/navigation";

export default function AccountDetailPage() {
  const { operator, loading } = useRequireAuth();
  const params = useParams<{ id: string }>();
  const accountId = Number(params.id);

  if (loading || !operator) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载中…
      </div>
    );
  }

  if (!Number.isInteger(accountId) || accountId <= 0) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-red-700">
        无效的账号 ID
      </div>
    );
  }

  return <AccountDetail accountId={accountId} operator={operator} />;
}
