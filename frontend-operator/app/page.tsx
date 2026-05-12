"use client";

import { OperatorDashboard } from "@/components/dashboard";
import { useRequireAuth } from "@/lib/auth";

export default function Home() {
  const { operator, loading } = useRequireAuth();

  if (loading || !operator) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载中…
      </div>
    );
  }

  return <OperatorDashboard operator={operator} />;
}
