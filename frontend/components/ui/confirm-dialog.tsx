"use client";

import { useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConfirmStore } from "@/lib/stores/confirm-store";
import { cn } from "@/lib/utils";

export function ConfirmDialog() {
  const { isOpen, options, close } = useConfirmStore();

  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close(false);
      if (e.key === "Enter") close(true);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, close]);

  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen]);

  if (!isOpen || !options) return null;

  const variant = options.variant ?? "default";
  const confirmText = options.confirmText ?? "Confirmar";
  const cancelText = options.cancelText ?? "Cancelar";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => close(false)}
        aria-hidden="true"
      />

      <div
        className={cn(
          "relative z-10 w-full max-w-md rounded-xl border",
          "border-[var(--color-border-strong)] bg-[var(--color-surface)]",
          "shadow-2xl",
        )}
      >
        <div className="flex items-start gap-3 p-5 pb-4">
          {variant === "danger" && (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--color-danger)]/10">
              <AlertTriangle className="h-5 w-5 text-[var(--color-danger)]" />
            </div>
          )}

          <div className="min-w-0 flex-1">
            <h2
              id="confirm-title"
              className="text-base font-semibold tracking-tight"
            >
              {options.title}
            </h2>
            {options.message && (
              <p className="mt-1.5 text-sm leading-relaxed text-[var(--color-muted)]">
                {options.message}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={() => close(false)}
            className="shrink-0 rounded p-1 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] p-4">
          <Button variant="secondary" onClick={() => close(false)}>
            {cancelText}
          </Button>
          <Button
            onClick={() => close(true)}
            className={cn(
              variant === "danger" &&
                "bg-[var(--color-danger)] text-white hover:bg-[var(--color-danger)]/90",
            )}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}