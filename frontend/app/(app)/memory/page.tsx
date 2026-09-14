"use client";

import { useState } from "react";
import { Brain, Plus, X } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MemoryCard } from "@/components/memory/memory-card";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useCreateMemory, useMemories } from "@/lib/hooks/use-memory";
import type { MemoryStatus, MemoryType } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const TYPE_OPTIONS: { value: MemoryType; label: string }[] = [
  { value: "FACT", label: "Hecho" },
  { value: "PREFERENCE", label: "Preferencia" },
  { value: "GOAL", label: "Meta" },
  { value: "INSTRUCTION", label: "Instrucción" },
  { value: "EPISODE", label: "Episodio" },
];

const STATUS_TABS: { value: MemoryStatus; label: string }[] = [
  { value: "ACTIVE", label: "Activas" },
  { value: "SUPERSEDED", label: "Reemplazadas" },
  { value: "DELETED", label: "Eliminadas" },
];

export default function MemoryPage() {
  const { data: user } = useCurrentUser();
  const [status, setStatus] = useState<MemoryStatus>("ACTIVE");
  const { data: memories, isLoading } = useMemories(status);
  const createMutation = useCreateMemory();

  const [creating, setCreating] = useState(false);
  const [newType, setNewType] = useState<MemoryType>("FACT");
  const [newContent, setNewContent] = useState("");

  if (!user) return null;

  function submitCreate() {
    const trimmed = newContent.trim();
    if (trimmed.length < 3) return;
    createMutation.mutate(
      { type: newType, content: trimmed },
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
      <Header title="Memoria" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Memoria</h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Lo que ELI recuerda de ti entre conversaciones. Puedes
                revisarlo, editarlo o borrarlo en cualquier momento.
              </p>
            </div>
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="h-3.5 w-3.5" />
              Nueva
            </Button>
          </div>

          {/* Filtro por estado */}
          <div className="mt-6 flex gap-1 border-b border-[var(--color-border)]">
            {STATUS_TABS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setStatus(t.value)}
                className={cn(
                  "border-b-2 px-3 py-2 text-sm transition-colors",
                  status === t.value
                    ? "border-[var(--color-primary)] text-[var(--color-foreground)]"
                    : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-foreground)]",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Formulario de creación */}
          {creating && (
            <div className="mt-4 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Nueva memoria</p>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setNewContent("");
                  }}
                  className="text-[var(--color-subtle)] hover:text-[var(--color-foreground)]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-3 flex gap-2">
                {TYPE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setNewType(opt.value)}
                    className={cn(
                      "rounded-md border px-3 py-1 text-xs transition-colors",
                      newType === opt.value
                        ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                        : "border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-border-strong)]",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              <div className="mt-3">
                <Input
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="Ej: El usuario trabaja en finanzas y usa Excel a diario"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submitCreate();
                    if (e.key === "Escape") setCreating(false);
                  }}
                  autoFocus
                />
              </div>

              <div className="mt-3 flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setCreating(false);
                    setNewContent("");
                  }}
                >
                  Cancelar
                </Button>
                <Button
                  size="sm"
                  onClick={submitCreate}
                  disabled={newContent.trim().length < 3 || createMutation.isPending}
                >
                  Crear
                </Button>
              </div>
            </div>
          )}

          {/* Lista */}
          <div className="mt-6 space-y-3">
            {isLoading && (
              <p className="text-sm text-[var(--color-muted)]">Cargando…</p>
            )}
            {!isLoading && (!memories || memories.length === 0) && (
              <div className="rounded-lg border border-dashed border-[var(--color-border)] py-12 text-center">
                <Brain className="mx-auto h-8 w-8 text-[var(--color-subtle)]" />
                <p className="mt-3 text-sm text-[var(--color-muted)]">
                  {status === "ACTIVE"
                    ? "Aún no hay memorias. ELI irá guardando cosas cuando las cuentes, o puedes crearlas tú."
                    : "Sin memorias en este estado."}
                </p>
              </div>
            )}
            {memories?.map((m) => (
              <MemoryCard key={m.id} memory={m} />
            ))}
          </div>
        </div>
      </main>
    </>
  );
}