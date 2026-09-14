"use client";

import { Calculator, Calendar, Globe, Link2, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Tool } from "@/lib/api/types";

interface ToolCardProps {
  tool: Tool;
  selected: boolean;
  onSelect: () => void;
  userAutonomyLevel: number;
}

const ICONS: Record<string, React.ElementType> = {
  calculator: Calculator,
  datetime: Calendar,
  web_search: Globe,
  web_fetch: Link2,
};

export function ToolCard({
  tool,
  selected,
  onSelect,
  userAutonomyLevel,
}: ToolCardProps) {
  const Icon = ICONS[tool.name] ?? Lock;
  const allowed = tool.min_autonomy_level <= userAutonomyLevel;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-strong)]",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
          allowed
            ? "bg-[var(--color-surface-hover)] text-[var(--color-primary)]"
            : "bg-[var(--color-surface-hover)] text-[var(--color-subtle)]",
        )}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{tool.name}</p>
          {!allowed && (
            <span className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              Bloqueada
            </span>
          )}
          {tool.requires_confirmation && allowed && (
            <span className="rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-400">
              Sensible
            </span>
          )}
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-[var(--color-muted)]">
          {tool.description}
        </p>
        <p className="mt-1.5 text-[10px] text-[var(--color-subtle)]">
          Nivel {tool.min_autonomy_level}+ · timeout {tool.timeout_ms} ms
        </p>
      </div>
    </button>
  );
}