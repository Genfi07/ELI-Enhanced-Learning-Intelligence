"use client";

import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Flow } from "@/lib/constants/flows";

interface FlowCardProps {
  flow: Flow;
  onUse: () => void;
}

export function FlowCard({ flow, onUse }: FlowCardProps) {
  const Icon = flow.icon;
  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-[var(--color-border)]",
        "bg-[var(--color-surface)] p-4 transition-colors",
        "hover:border-[var(--color-border-strong)]",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            "bg-[var(--color-surface-hover)]",
            flow.accent,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight">
            {flow.title}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">
            {flow.description}
          </p>
        </div>
      </div>

      {flow.hint && (
        <p className="text-[11px] italic text-[var(--color-subtle)]">
          Ejemplo: {flow.hint}
        </p>
      )}

      <div className="mt-auto flex justify-end">
        <Button size="sm" variant="secondary" onClick={onUse}>
          Usar flujo
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </article>
  );
}