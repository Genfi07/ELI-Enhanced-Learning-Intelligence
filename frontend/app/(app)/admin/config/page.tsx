"use client";

import { useMemo, useState } from "react";
import {
  Settings,
  RotateCcw,
  Save,
  Sparkles,
  Brain,
  FileSearch,
  Wrench,
  Coins,
  Layers,
  Shield,
  Eye,
  Search,
  Lightbulb,
  BookOpen,
  type LucideIcon,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfigGuideDialog } from "@/components/admin/config-guide-dialog";
import { SettingHelp } from "@/components/admin/setting-help";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import {
  useConfigGuide,
  useDeleteSetting,
  useResetAllSettings,
  useSettings,
  useUpdateSetting,
  type SettingItem,
} from "@/lib/hooks/use-admin";
import { cn } from "@/lib/utils";
import { useConfirm } from "@/lib/stores/confirm-store";

interface CategoryMeta {
  label: string;
  description: string;
  icon: LucideIcon;
  accent: string;
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  llm: {
    label: "Modelos de lenguaje",
    description: "Proveedor, modelo y parámetros de generación.",
    icon: Sparkles,
    accent: "text-violet-400",
  },
  embeddings: {
    label: "Embeddings",
    description: "Vectorización de texto para búsqueda semántica.",
    icon: Layers,
    accent: "text-cyan-400",
  },
  memory: {
    label: "Memoria",
    description: "Cómo ELI recuerda y consolida información.",
    icon: Brain,
    accent: "text-pink-400",
  },
  rag: {
    label: "RAG",
    description: "Recuperación aumentada: chunks, top-k, re-ranking.",
    icon: FileSearch,
    accent: "text-emerald-400",
  },
  tools: {
    label: "Herramientas",
    description: "Autonomía, confirmaciones y permisos de tools.",
    icon: Wrench,
    accent: "text-orange-400",
  },
  budgets: {
    label: "Presupuestos",
    description: "Límites de tokens y costes por turno / día.",
    icon: Coins,
    accent: "text-amber-400",
  },
  budget: {
    label: "Presupuestos",
    description: "Límites de tokens y costes por turno / día.",
    icon: Coins,
    accent: "text-amber-400",
  },
  reasoning: {
    label: "Razonamiento",
    description: "Planificación, resúmenes y profundidad de pensamiento.",
    icon: Lightbulb,
    accent: "text-indigo-400",
  },
  security: {
    label: "Seguridad",
    description: "Sesiones, rate limits y políticas de acceso.",
    icon: Shield,
    accent: "text-red-400",
  },
  auth: {
    label: "Autenticación",
    description: "Métodos de login y sesiones.",
    icon: Shield,
    accent: "text-red-400",
  },
  vision: {
    label: "Visión",
    description: "Extracción de imágenes y OCR.",
    icon: Eye,
    accent: "text-blue-400",
  },
  general: {
    label: "General",
    description: "Ajustes varios del sistema.",
    icon: Settings,
    accent: "text-zinc-400",
  },
};

function metaFor(category: string): CategoryMeta {
  return (
    CATEGORY_META[category] ?? {
      label: category.charAt(0).toUpperCase() + category.slice(1),
      description: `Configuración de ${category}`,
      icon: Settings,
      accent: "text-zinc-400",
    }
  );
}

export default function AdminConfigPage() {
  const { data: user } = useCurrentUser();

  const { data: settings, isLoading } = useSettings();
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);

  const resetMutation = useResetAllSettings();
  const confirm = useConfirm();
  const { data: guide } = useConfigGuide();

  const guideByKey = useMemo(() => {
    const acc: Record<string, string> = {};
    for (const e of guide ?? []) acc[e.key] = e.short;
    return acc;
  }, [guide]);

  async function handleResetAll() {
    const ok = await confirm({
      title: "Restablecer configuración",
      message:
        "Se eliminarán TODOS los overrides y cada valor volverá al predeterminado. Esta acción no se puede deshacer.",
      confirmText: "Restablecer todo",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    resetMutation.mutate();
  }

  const categories = useMemo(() => {
    const counts: Record<string, { total: number; overrides: number }> = {};
    for (const s of settings ?? []) {
      const c = (counts[s.category] ??= { total: 0, overrides: 0 });
      c.total += 1;
      if (s.is_override) c.overrides += 1;
    }
    return counts;
  }, [settings]);

  const grouped = useMemo(() => {
    const filtered = (settings ?? []).filter((s) => {
      if (activeCategory && s.category !== activeCategory) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return (
          s.key.toLowerCase().includes(q) ||
          (s.description ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
    return filtered.reduce<Record<string, SettingItem[]>>((acc, s) => {
      (acc[s.category] ??= []).push(s);
      return acc;
    }, {});
  }, [settings, search, activeCategory]);

  if (!user) return null;

  const totalSettings = settings?.length ?? 0;
  const totalOverrides = Object.values(categories).reduce(
    (n, c) => n + c.overrides,
    0,
  );

  return (
    <>
      <Header title="Admin · Configuración" user={user} />
      <main className="flex-1 overflow-y-auto min-h-0">
        <div className="mx-auto w-full max-w-4xl px-3 py-6 md:px-6 md:py-8">
          {/* Hero */}
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
                Configuración
              </h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Valores dinámicos de ELI. Los cambios se aplican al instante y
                quedan auditados.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[var(--color-muted)]">
                  {totalSettings} valores
                </span>
                {totalOverrides > 0 && (
                  <span className="rounded bg-[var(--color-primary)]/15 px-2 py-0.5 font-medium text-[var(--color-primary)]">
                    {totalOverrides} override{totalOverrides === 1 ? "" : "s"}
                  </span>
                )}
              </div>
            </div>

            <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row md:items-center">
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setGuideOpen(true)}
                  title="Ver guía de configuración"
                >
                  <BookOpen className="h-3.5 w-3.5" />
                  Ver guía
                </Button>
                {totalOverrides > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleResetAll}
                    disabled={resetMutation.isPending}
                    title="Restablecer todos los valores por defecto"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    {resetMutation.isPending
                      ? "Restableciendo…"
                      : "Restablecer todo"}
                  </Button>
                )}
              </div>
              <div className="relative w-full md:w-64">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-subtle)]" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar clave o descripción…"
                  className="pl-8"
                />
              </div>
            </div>
          </div>

          {/* Chips de categorías */}
          {Object.keys(categories).length > 0 && (
            <div className="mt-6 flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => setActiveCategory(null)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors",
                  activeCategory === null
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                    : "border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-foreground)]",
                )}
              >
                Todas
              </button>
              {Object.entries(categories).map(([cat, counts]) => {
                const meta = metaFor(cat);
                const Icon = meta.icon;
                const active = activeCategory === cat;
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setActiveCategory(active ? null : cat)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
                      active
                        ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                        : "border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-foreground)]",
                    )}
                  >
                    <Icon className="h-3 w-3" />
                    {meta.label}
                    <span className="text-[10px] opacity-60">
                      {counts.total}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {isLoading && (
            <p className="mt-8 text-sm text-[var(--color-muted)]">Cargando…</p>
          )}

          {/* Cards por categoría */}
          <div className="mt-6 space-y-6">
            {Object.entries(grouped).map(([category, items]) => (
              <CategoryCard
                key={category}
                category={category}
                items={items}
                overrides={categories[category]?.overrides ?? 0}
                guideByKey={guideByKey}
              />
            ))}

            {!isLoading && Object.keys(grouped).length === 0 && (
              <p className="py-12 text-center text-sm text-[var(--color-muted)]">
                No hay valores que coincidan con el filtro.
              </p>
            )}
          </div>
        </div>
      </main>

      <ConfigGuideDialog
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
      />
    </>
  );
}

function CategoryCard({
  category,
  items,
  overrides,
  guideByKey,
}: {
  category: string;
  items: SettingItem[];
  overrides: number;
  guideByKey: Record<string, string>;
}) {
  const meta = metaFor(category);
  const Icon = meta.icon;

  return (
    <section className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <header className="flex flex-col gap-2 border-b border-[var(--color-border)] px-4 py-3 md:flex-row md:items-start md:justify-between md:gap-4 md:px-5 md:py-4">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-surface-hover)]",
              meta.accent,
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold tracking-tight">
              {meta.label}
            </h2>
            <p className="mt-0.5 text-xs text-[var(--color-muted)]">
              {meta.description}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 pl-12 text-[10px] md:pl-0">
          <span className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 uppercase tracking-wider text-[var(--color-subtle)]">
            {items.length} valor{items.length === 1 ? "" : "es"}
          </span>
          {overrides > 0 && (
            <span className="rounded bg-[var(--color-primary)]/15 px-1.5 py-0.5 font-medium uppercase tracking-wider text-[var(--color-primary)]">
              {overrides} override{overrides === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </header>

      <div className="divide-y divide-[var(--color-border)]">
        {items.map((s) => (
          <SettingRow key={s.key} item={s} helpText={guideByKey[s.key]} />
        ))}
      </div>
    </section>
  );
}

function SettingRow({
  item,
  helpText,
}: {
  item: SettingItem;
  helpText?: string;
}) {
  const [draft, setDraft] = useState(() => {
    if (typeof item.value === "string") return item.value;
    if (item.value === null || item.value === undefined) return "";
    return JSON.stringify(item.value);
  });
  const updateMutation = useUpdateSetting();
  const deleteMutation = useDeleteSetting();

  const isBool = typeof item.default === "boolean";
  const isNum = typeof item.default === "number";
  const defaultValue = formatValue(item.default, isBool, isNum);
  const dirty = draft !== formatValue(item.value, isBool, isNum);

  function save() {
    let parsed: unknown = draft;
    if (isBool) {
      parsed = draft === "true";
    } else if (isNum) {
      const n = Number(draft);
      if (Number.isNaN(n)) return;
      parsed = n;
    } else if (draft.startsWith("[") || draft.startsWith("{")) {
      try {
        parsed = JSON.parse(draft);
      } catch {
        return;
      }
    }
    updateMutation.mutate({ key: item.key, value: parsed });
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-2 px-4 py-3 transition-colors md:flex-row md:items-start md:gap-4 md:px-5",
        item.is_override && "bg-[var(--color-primary-soft)]",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <code className="break-all text-xs font-medium text-[var(--color-foreground)]">
            {item.key}
          </code>
          <SettingHelp short={helpText ?? ""} />
          {item.is_override ? (
            <span className="rounded bg-[var(--color-primary)]/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-primary)]">
              Override
            </span>
          ) : (
            <span className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              Default
            </span>
          )}
        </div>
        {item.description && (
          <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">
            {item.description}
          </p>
        )}
        {!item.is_override && defaultValue !== "" && (
          <p className="mt-1 break-all text-[10px] text-[var(--color-subtle)]">
            Valor por defecto:{" "}
            <span className="font-mono">{defaultValue}</span>
          </p>
        )}
      </div>

      <div className="flex w-full shrink-0 items-center gap-1.5 md:w-auto">
        <div className="min-w-0 flex-1 md:w-56 md:flex-none">
          {isBool ? (
            <select
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs focus:border-[var(--color-primary)] focus:outline-none"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-8 w-full font-mono text-xs"
            />
          )}
        </div>

        <div className="flex w-16 shrink-0 justify-end gap-1">
          {dirty && (
            <Button
              size="sm"
              onClick={save}
              disabled={updateMutation.isPending}
              className="h-8 px-2"
              title="Guardar"
            >
              <Save className="h-3.5 w-3.5" />
            </Button>
          )}
          {item.is_override && !dirty && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => deleteMutation.mutate(item.key)}
              disabled={deleteMutation.isPending}
              className="h-8 px-2"
              title="Quitar override"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function formatValue(v: unknown, isBool: boolean, isNum: boolean): string {
  if (v === null || v === undefined) return "";
  if (isBool || isNum) return String(v);
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}