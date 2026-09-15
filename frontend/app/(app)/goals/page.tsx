"use client";

import { useState } from "react";
import { Target, Plus, X } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GoalCard } from "@/components/goals/goal-card";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useCreateGoal, useGoals } from "@/lib/hooks/use-goals";
import type { GoalKind, GoalStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_TABS: { value: GoalStatus; label: string }[] = [
  { value: "ACTIVE", label: "Activas" },
  { value: "PAUSED", label: "En pausa" },
  { value: "ACHIEVED", label: "Cumplidas" },
  { value: "ABANDONED", label: "Abandonadas" },
];

const KIND_OPTIONS: { value: GoalKind; label: string }[] = [
  { value: "LEARN", label: "Aprender" },
  { value: "EXPLORE", label: "Explorar" },
  { value: "IMPROVE", label: "Mejorar" },
  { value: "CONNECT", label: "Conectar" },
  { value: "PROPOSE", label: "Proponer" },
];

export default function GoalsPage() {
  const { data: user } = useCurrentUser();
  const [status, setStatus] = useState<GoalStatus>("ACTIVE");
  const { data: goals, isLoading } = useGoals(status);
  const createMutation = useCreateGoal();

  const [creating, setCreating] = useState(false);
  const [newKind, setNewKind] = useState<GoalKind>("LEARN");
  const [newContent, setNewContent] = useState("");
  const [newPriority, setNewPriority] = useState(3);

  if (!user) return null;

  const canEdit = user.role === "ADMIN" || user.role === "SUPER_ADMIN";

  function submitCreate() {
    const trimmed = newContent.trim();
    if (trimmed.length < 5) return;
    createMutation.mutate(
      {
        kind: newKind,
        content: trimmed,
        priority: newPriority,
      },
      {
        onSuccess: () => {
          setNewContent("");
          setCreating(false);
        },
      },
    );
  }

  return (
    <>
      <Header title="Metas" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Metas</h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Las metas propias de ELI. Se crean automáticamente cuando
                detecta un patrón, o cuando tú se las enseñas.
              </p>
            </div>
            {canEdit && (
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus className="h-3.5 w-3.5" />
                Nueva
              </Button>
            )}
          </div>

          {/* Formulario de creación (solo admin) */}
          {creating && canEdit && (
            <div className="mt-6 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Nueva meta para ELI</p>
                <button
                  type="button"
                  onClick={() => setCreating(false)}
                  className="rounded p-1 text-[var(--color-subtle)] hover:bg-[var(--color-surface-hover)]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-3 space-y-3">
                <div>
                  <label className="text-xs text-[var(--color-subtle)]">
                    Tipo
                  </label>
                  <select
                    value={newKind}
                    onChange={(e) => setNewKind(e.target.value as GoalKind)}
                    className="mt-1 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-primary)] focus:outline-none"
                  >
                    {KIND_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs text-[var(--color-subtle)]">
                    Contenido
                  </label>
                  <Input
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                    placeholder="Ej: Entender los embeddings multilingües"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitCreate();
                    }}
                  />
                </div>

                <div>
                  <label className="text-xs text-[var(--color-subtle)]">
                    Prioridad (1-5)
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={5}
                    value={newPriority}
                    onChange={(e) => setNewPriority(Number(e.target.value))}
                  />
                </div>

                <div className="flex justify-end">
                  <Button
                    size="sm"
                    onClick={submitCreate}
                    disabled={
                      createMutation.isPending || newContent.trim().length < 5
                    }
                  >
                    Crear meta
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Tabs de estado */}
          <div className="mt-6 flex gap-1 border-b border-[var(--color-border)]">
            {STATUS_TABS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setStatus(t.value)}
                className={cn(
                  "relative px-3 py-2 text-sm transition-colors",
                  status === t.value
                    ? "text-[var(--color-foreground)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]",
                )}
              >
                {t.label}
                {status === t.value && (
                  <span className="absolute inset-x-0 -bottom-px h-0.5 bg-[var(--color-primary)]" />
                )}
              </button>
            ))}
          </div>

          {/* Listado */}
          <div className="mt-4 space-y-2">
            {isLoading && (
              <p className="text-sm text-[var(--color-muted)]">Cargando…</p>
            )}

            {!isLoading && (!goals || goals.length === 0) && (
              <div className="rounded-lg border border-dashed border-[var(--color-border)] py-12 text-center">
                <Target className="mx-auto h-8 w-8 text-[var(--color-subtle)]" />
                <p className="mt-3 text-sm text-[var(--color-muted)]">
                  {status === "ACTIVE"
                    ? "ELI no tiene metas activas ahora mismo."
                    : "No hay metas en este estado."}
                </p>
                <p className="mt-1 text-xs text-[var(--color-subtle)]">
                  Las metas se crean cuando ELI detecta un patrón o cuando
                  se las enseñas en el chat.
                </p>
              </div>
            )}

            {goals?.map((goal) => (
              <GoalCard key={goal.id} goal={goal} canEdit={canEdit} />
            ))}
          </div>
        </div>
      </main>
    </>
  );
}