"use client";

import { useState } from "react";
import { Settings, RotateCcw, Save } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import {
  useDeleteSetting,
  useSettings,
  useUpdateSetting,
  type SettingItem,
} from "@/lib/hooks/use-admin";
import { cn } from "@/lib/utils";

export default function AdminConfigPage() {
  const { data: user } = useCurrentUser();
  const { data: settings, isLoading } = useSettings();

  if (!user) return null;

  // Agrupar por categoría
  const grouped = (settings ?? []).reduce<Record<string, SettingItem[]>>(
    (acc, s) => {
      (acc[s.category] ??= []).push(s);
      return acc;
    },
    {},
  );

  return (
    <>
      <Header title="Admin · Configuración" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">
            Configuración
          </h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Valores dinámicos de ELI. Los cambios se aplican al instante y
            quedan auditados.
          </p>

          {isLoading && (
            <p className="mt-6 text-sm text-[var(--color-muted)]">Cargando…</p>
          )}

          <div className="mt-8 space-y-8">
            {Object.entries(grouped).map(([category, items]) => (
              <section key={category}>
                <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
                  <Settings className="h-3 w-3" />
                  {category}
                </h2>
                <div className="space-y-2">
                  {items.map((s) => (
                    <SettingRow key={s.key} item={s} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}

function SettingRow({ item }: { item: SettingItem }) {
  const [draft, setDraft] = useState(() => {
    if (typeof item.value === "string") return item.value;
    return JSON.stringify(item.value);
  });
  const updateMutation = useUpdateSetting();
  const deleteMutation = useDeleteSetting();

  const isBool = typeof item.default === "boolean";
  const isNum = typeof item.default === "number";
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
        "rounded-lg border p-3 transition-colors",
        item.is_override
          ? "border-[var(--color-primary)]/30 bg-[var(--color-primary-soft)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)]",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <code className="text-xs font-medium text-[var(--color-foreground)]">
              {item.key}
            </code>
            {item.is_override && (
              <span className="rounded bg-[var(--color-primary)]/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-[var(--color-primary)]">
                Override
              </span>
            )}
          </div>
          {item.description && (
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              {item.description}
            </p>
          )}
          {!item.is_override && (
            <p className="mt-1 text-[10px] text-[var(--color-subtle)]">
              default: {formatValue(item.default, isBool, isNum)}
            </p>
          )}
        </div>

        <div className="flex w-64 shrink-0 items-center gap-1">
          {isBool ? (
            <select
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-1.5 text-xs focus:border-[var(--color-primary)] focus:outline-none"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-8 text-xs"
            />
          )}

          {dirty && (
            <Button
              size="sm"
              onClick={save}
              disabled={updateMutation.isPending}
              className="h-8 shrink-0 px-2"
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
              className="h-8 shrink-0 px-2"
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