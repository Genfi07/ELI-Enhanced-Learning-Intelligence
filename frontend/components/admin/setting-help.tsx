"use client";

import { useState } from "react";
import { HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface SettingHelpProps {
  /** Texto corto para el tooltip (normalmente el `short` de la guía). */
  short: string;
  /** Si no hay guía para esta clave, se muestra un texto por defecto. */
  fallback?: string;
  className?: string;
}

/**
 * Icono `?` que al pasar el mouse muestra un tooltip con la descripción corta
 * de la configuración. Para detalle completo, el usuario pulsa "Ver guía".
 */
export function SettingHelp({
  short,
  fallback = "Sin descripción disponible.",
  className,
}: SettingHelpProps) {
  const [open, setOpen] = useState(false);
  const text = short || fallback;

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <button
        type="button"
        tabIndex={0}
        aria-label={text}
        className="flex h-4 w-4 items-center justify-center rounded-full text-[var(--color-subtle)] transition-colors hover:text-[var(--color-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>

      {open && (
        <span
          role="tooltip"
          className={cn(
            "pointer-events-none absolute left-1/2 top-full z-40 mt-2 w-72 -translate-x-1/2",
            "rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)]",
            "px-3 py-2 text-xs leading-relaxed text-[var(--color-muted)]",
            "shadow-xl shadow-black/40",
          )}
        >
          {text}
        </span>
      )}
    </span>
  );
}