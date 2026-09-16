"use client";

import { useMemo, useState } from "react";
import {
  BookOpen,
  Search,
  Settings,
  Sparkles,
  Brain,
  FileSearch,
  Wrench,
  Coins,
  Layers,
  Shield,
  Eye,
  Lightbulb,
  X,
  type LucideIcon,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useConfigGuide, type GuideEntry } from "@/lib/hooks/use-admin";
import { cn } from "@/lib/utils";

// --------------------------------------------------------------------------- //
// Metadatos por categoría (mismo mapa que en la página de config)
// --------------------------------------------------------------------------- //
interface CategoryMeta {
  label: string;
  icon: LucideIcon;
  accent: string;
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  llm: { label: "Modelos de lenguaje", icon: Sparkles, accent: "text-violet-400" },
  embeddings: { label: "Embeddings", icon: Layers, accent: "text-cyan-400" },
  memory: { label: "Memoria", icon: Brain, accent: "text-pink-400" },
  rag: { label: "RAG", icon: FileSearch, accent: "text-emerald-400" },
  tools: { label: "Herramientas", icon: Wrench, accent: "text-orange-400" },
  budgets: { label: "Presupuestos", icon: Coins, accent: "text-amber-400" },
  budget: { label: "Presupuestos", icon: Coins, accent: "text-amber-400" },
  reasoning: { label: "Razonamiento", icon: Lightbulb, accent: "text-indigo-400" },
  security: { label: "Seguridad", icon: Shield, accent: "text-red-400" },
  auth: { label: "Autenticación", icon: Shield, accent: "text-red-400" },
  vision: { label: "Visión", icon: Eye, accent: "text-blue-400" },
  general: { label: "General", icon: Settings, accent: "text-zinc-400" },
};

function metaFor(category: string): CategoryMeta {
  return (
    CATEGORY_META[category] ?? {
      label: category.charAt(0).toUpperCase() + category.slice(1),
      icon: Settings,
      accent: "text-zinc-400",
    }
  );
}

// --------------------------------------------------------------------------- //
// Modal
// --------------------------------------------------------------------------- //
interface ConfigGuideDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ConfigGuideDialog({ open, onClose }: ConfigGuideDialogProps) {
  const { data: guide, isLoading } = useConfigGuide();
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const categories = useMemo(() => {
    const acc: Record<string, number> = {};
    for (const e of guide ?? []) {
      acc[e.category] = (acc[e.category] ?? 0) + 1;
    }
    return acc;
  }, [guide]);

  const filtered = useMemo(() => {
    return (guide ?? []).filter((e) => {
      if (activeCategory && e.category !== activeCategory) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return (
          e.key.toLowerCase().includes(q) ||
          e.short.toLowerCase().includes(q) ||
          e.description.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [guide, search, activeCategory]);

  const grouped = useMemo(() => {
    return filtered.reduce<Record<string, GuideEntry[]>>((acc, e) => {
      (acc[e.category] ??= []).push(e);
      return acc;
    }, {});
  }, [filtered]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative z-10 flex h-[85vh] w-full max-w-5xl overflow-hidden rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-2xl">
        {/* Header */}
        <div className="flex w-full flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
                <BookOpen className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-base font-semibold tracking-tight">
                  Guía de configuración
                </h2>
                <p className="text-xs text-[var(--color-muted)]">
                  Qué hace cada valor, qué opciones acepta y qué impacto tiene.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
              aria-label="Cerrar"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex min-h-0 flex-1">
            {/* Sidebar categorías */}
            <aside className="w-56 shrink-0 overflow-y-auto border-r border-[var(--color-border)] p-3">
              <button
                type="button"
                onClick={() => setActiveCategory(null)}
                className={cn(
                  "mb-1 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-xs transition-colors",
                  activeCategory === null
                    ? "bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                    : "text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
                )}
              >
                <BookOpen className="h-3.5 w-3.5" />
                Todas
                <span className="ml-auto text-[10px] opacity-60">
                  {guide?.length ?? 0}
                </span>
              </button>
              {Object.entries(categories).map(([cat, count]) => {
                const meta = metaFor(cat);
                const Icon = meta.icon;
                const active = activeCategory === cat;
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setActiveCategory(active ? null : cat)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs transition-colors",
                      active
                        ? "bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                        : "text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
                    )}
                  >
                    <Icon className={cn("h-3.5 w-3.5", meta.accent)} />
                    <span className="truncate">{meta.label}</span>
                    <span className="ml-auto text-[10px] opacity-60">
                      {count}
                    </span>
                  </button>
                );
              })}
            </aside>

            {/* Contenido */}
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="border-b border-[var(--color-border)] p-3">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-subtle)]" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar por clave o descripción…"
                    className="pl-8"
                  />
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                {isLoading && (
                  <p className="text-sm text-[var(--color-muted)]">Cargando…</p>
                )}

                {!isLoading && Object.keys(grouped).length === 0 && (
                  <p className="py-12 text-center text-sm text-[var(--color-muted)]">
                    No hay entradas que coincidan.
                  </p>
                )}

                <div className="space-y-6">
                  {Object.entries(grouped).map(([category, entries]) => {
                    const meta = metaFor(category);
                    const Icon = meta.icon;
                    return (
                      <section key={category}>
                        <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-subtle)]">
                          <Icon className={cn("h-3.5 w-3.5", meta.accent)} />
                          {meta.label}
                        </h3>
                        <div className="space-y-2">
                          {entries.map((e) => (
                            <GuideCard key={e.key} entry={e} />
                          ))}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GuideCard({ entry }: { entry: GuideEntry }) {
  return (
    <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-3">
      <code className="text-xs font-medium text-[var(--color-foreground)]">
        {entry.key}
      </code>
      <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-muted)]">
        {entry.description}
      </p>

      <div className="mt-2 space-y-1 text-[11px]">
        {entry.values && (
          <div className="flex gap-2">
            <span className="shrink-0 font-medium text-[var(--color-subtle)]">
              Valores:
            </span>
            <span className="font-mono text-[var(--color-foreground)]">
              {entry.values}
            </span>
          </div>
        )}
        {entry.example && (
          <div className="flex gap-2">
            <span className="shrink-0 font-medium text-[var(--color-subtle)]">
              Ejemplo:
            </span>
            <span className="font-mono text-[var(--color-foreground)]">
              {entry.example}
            </span>
          </div>
        )}
        {entry.impact && (
          <div className="flex gap-2 rounded bg-[var(--color-danger)]/5 px-2 py-1">
            <span className="shrink-0 font-medium text-[var(--color-danger)]">
              ⚠ Impacto:
            </span>
            <span className="text-[var(--color-muted)]">{entry.impact}</span>
          </div>
        )}
      </div>
    </article>
  );
}