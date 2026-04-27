import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "success" | "danger" | "transfer";

const tones: Record<BadgeTone, string> = {
  neutral: "border-border/80 bg-muted/70 text-muted-foreground",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  danger: "border-red-200 bg-red-50 text-red-700",
  transfer: "border-blue-200 bg-blue-50 text-blue-700"
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em]",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
