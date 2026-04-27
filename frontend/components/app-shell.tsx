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
  const activeMeta = sections.find((section) => section.id === activeSection) ?? sections[0];

  return (
    <div className="min-h-screen bg-background">
      <div className="grid min-h-screen lg:grid-cols-[296px_1fr]">
        <aside className="border-b border-[#28443c] bg-[linear-gradient(180deg,#18352e_0%,#122722_100%)] text-white lg:sticky lg:top-0 lg:h-screen lg:overflow-hidden lg:border-b-0 lg:border-r">
          <div className="flex h-full min-h-0 flex-col">
            <div className="border-b border-white/10 px-5 py-6">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 text-white shadow-[0_10px_30px_rgba(0,0,0,0.18)]">
                  <BadgeDollarSign className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold">Finance System</div>
                  <div className="truncate text-xs text-white/60">freeman27315-coder</div>
                </div>
              </div>
              <p className="mt-5 text-sm leading-6 text-white/62">多钱包资金、供应商往来和业务模块视图。</p>
            </div>

            <nav className="sidebar-scroll grid gap-2 p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
              {sections.map((section) => {
                const Icon = icons[section.id as keyof typeof icons] ?? LayoutDashboard;
                const active = activeSection === section.id;

                return (
                  <Link
                    key={section.id}
                    href={section.href}
                    className={cn(
                      "rounded-2xl border border-transparent px-4 py-3 transition-all",
                      active
                        ? "border-white/10 bg-white/10 shadow-[0_12px_32px_rgba(0,0,0,0.16)]"
                        : "text-white/72 hover:border-white/8 hover:bg-white/6 hover:text-white"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={cn(
                          "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
                          active ? "bg-white text-[#143129]" : "bg-white/8 text-white"
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      </div>
                      <div className="min-w-0">
                        <div className={cn("truncate text-sm font-semibold", active ? "text-white" : "text-white/86")}>
                          {section.title}
                        </div>
                        <div className="mt-1 line-clamp-2 text-xs leading-5 text-white/58">{section.description}</div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-10 border-b border-border/70 bg-background/88 backdrop-blur-xl">
            <div className="mx-auto flex min-h-20 max-w-7xl flex-col justify-center gap-3 px-4 py-4 md:px-6 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-muted-foreground">
                  <span>FUNDS CONTROL</span>
                  <span className="h-1 w-1 rounded-full bg-success" />
                  <span>{activeMeta.title}</span>
                </div>
                <h1 className="mt-1 text-xl font-semibold tracking-normal md:text-2xl">资金仪表盘</h1>
                <p className="mt-1 text-sm text-muted-foreground">{activeMeta.description}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge>LIVE VIEW</Badge>
                <Badge tone="transfer">FASTAPI / MOCK</Badge>
                <Badge tone="success">MINOR UNIT SAFE</Badge>
              </div>
            </div>
          </header>

          <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-7">{children}</main>
        </div>
      </div>
    </div>
  );
}
