"use client";

import { OperatorWorkbench } from "@/components/workbench";
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

  return <OperatorWorkbench operator={operator} />;
}
