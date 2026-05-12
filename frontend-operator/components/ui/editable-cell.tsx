"use client";

import { Check, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// ===================================================================
// 通用 inline 可编辑单元格 (CEO 2026-05-12)
// 点击 → 变 input/select → blur 自动保存 (调用 onSave)
// onSave 返回 Promise,期间显示 spinner; 成功显示 ✓ 一闪
// ===================================================================

type State = "idle" | "saving" | "saved" | "error";

export function EditableTextCell({
  value,
  placeholder,
  onSave,
  disabled = false,
  inputMode,
  className
}: {
  value: string | null;
  placeholder?: string;
  onSave: (newValue: string) => Promise<void>;
  disabled?: boolean;
  inputMode?: "text" | "decimal" | "numeric";
  className?: string;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [state, setState] = useState<State>("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  // 外部值变了同步进 draft (例如服务器返回新数据)
  useEffect(() => {
    if (state === "idle") setDraft(value ?? "");
  }, [value, state]);

  const commit = async () => {
    const next = draft.trim();
    const before = (value ?? "").trim();
    if (next === before) return; // 没改,不发请求
    setState("saving");
    try {
      await onSave(next);
      setState("saved");
      setTimeout(() => setState("idle"), 800);
    } catch (e) {
      setState("error");
      console.error("save failed", e);
      setTimeout(() => setState("idle"), 1500);
      // 回滚到原值
      setDraft(value ?? "");
    }
  };

  return (
    <div className={cn("relative", className)}>
      <input
        ref={inputRef}
        type="text"
        inputMode={inputMode}
        disabled={disabled || state === "saving"}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            (e.target as HTMLInputElement).blur();
          } else if (e.key === "Escape") {
            setDraft(value ?? "");
            (e.target as HTMLInputElement).blur();
          }
        }}
        className={cn(
          "h-8 w-full rounded border border-transparent bg-transparent px-2 text-sm outline-none transition-colors",
          "hover:border-border focus:border-primary focus:bg-card",
          state === "error" && "border-red-300 bg-red-50",
          state === "saved" && "bg-emerald-50",
          disabled && "cursor-not-allowed opacity-60"
        )}
      />
      <StateIcon state={state} />
    </div>
  );
}

export function EditableSelectCell<T extends string | number>({
  value,
  options,
  onSave,
  placeholder = "请选择",
  disabled = false,
  className
}: {
  value: T | null;
  options: { value: T; label: string }[];
  onSave: (newValue: T | null) => Promise<void>;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [state, setState] = useState<State>("idle");

  const commit = async (raw: string) => {
    let next: T | null = null;
    if (raw !== "") {
      next = (typeof (options[0]?.value ?? "") === "number"
        ? Number(raw)
        : raw) as T;
    }
    if (next === value) return;
    setState("saving");
    try {
      await onSave(next);
      setState("saved");
      setTimeout(() => setState("idle"), 800);
    } catch (e) {
      setState("error");
      console.error("save failed", e);
      setTimeout(() => setState("idle"), 1500);
    }
  };

  return (
    <div className={cn("relative", className)}>
      <select
        disabled={disabled || state === "saving"}
        value={value == null ? "" : String(value)}
        onChange={(e) => commit(e.target.value)}
        className={cn(
          "h-8 w-full rounded border border-transparent bg-transparent px-2 text-sm outline-none transition-colors",
          "hover:border-border focus:border-primary focus:bg-card",
          state === "error" && "border-red-300 bg-red-50",
          state === "saved" && "bg-emerald-50",
          disabled && "cursor-not-allowed opacity-60"
        )}
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
      <StateIcon state={state} />
    </div>
  );
}

function StateIcon({ state }: { state: State }) {
  if (state === "saving") {
    return (
      <Loader2
        className="pointer-events-none absolute right-1 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin text-blue-600"
        aria-hidden
      />
    );
  }
  if (state === "saved") {
    return (
      <Check
        className="pointer-events-none absolute right-1 top-1/2 h-3 w-3 -translate-y-1/2 text-emerald-600"
        aria-hidden
      />
    );
  }
  return null;
}
