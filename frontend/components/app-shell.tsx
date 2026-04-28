import {
  BadgeDollarSign,
  Building2,
  CircleDollarSign,
  Gamepad2,
  LayoutDashboard,
  Landmark,
  ShoppingBag
} from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { sections } from "@/lib/navigation";

const icons = {
  dashboard: LayoutDashboard,
  assets: CircleDollarSign,
  vendors: Building2,
  xbox: Gamepad2,
  taobao: ShoppingBag,
  taiwan: Landmark
};

type AppShellProps = {
  activeSection: string;
  children: React.ReactNode;
};

export function AppShell({ activeSection, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <div className="grid min-h-screen lg:grid-cols-[248px_1fr]">
        <aside className="border-b border-border bg-card lg:border-b-0 lg:border-r">
          <div className="flex h-full flex-col">
            <div className="flex h-16 items-center gap-3 border-b border-border px-5">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <BadgeDollarSign className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">Finance System</div>
                <div className="truncate text-xs text-muted-foreground">freeman27315-coder</div>
              </div>
            </div>

            <nav className="grid gap-1 p-3">
              {sections.map((section) => {
                const Icon = icons[section.id as keyof typeof icons] ?? LayoutDashboard;
                const active = activeSection === section.id;

                return (
                  <Link
                    key={section.id}
                    href={section.href}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                      active && "bg-muted text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{section.title}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto border-t border-border p-4">
              <Badge tone="transfer">Frontend Agent</Badge>
              <p className="mt-2 text-xs text-muted-foreground">0.1.0</p>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">Next.js Dashboard / API Proxy</p>
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-10 flex min-h-16 items-center justify-between gap-3 border-b border-border bg-background/95 px-4 backdrop-blur md:px-6">
            <div>
              <h1 className="text-lg font-semibold tracking-normal md:text-xl">资金仪表盘</h1>
              <p className="text-xs text-muted-foreground md:text-sm">多钱包、供应商和业务模块资金状态</p>
            </div>
            <Button variant="outline" size="sm">
              <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
              Dashboard
            </Button>
          </header>

          <main className="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
