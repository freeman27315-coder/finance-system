"use client";

import { AppShell } from "@/components/app-shell";
import { Dashboard } from "@/components/dashboard";

export default function HomePage() {
  return (
    <AppShell activeSection="dashboard">
      <Dashboard />
    </AppShell>
  );
}
