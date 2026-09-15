"use client";

import { useState } from "react";
import { Pencil, Trash2, X, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, formatRelativeDate } from "@/lib/utils";
import type { Memory, MemoryType } from "@/lib/api/types";
import {
  useDeleteMemory,
  useUpdateMemory,
} from "@/lib/hooks/use-memory";
import { useConfirm } from "@/lib/stores/confirm-store";

interface MemoryCardProps {
  memory: Memory;
}

const TYPE_LABEL: Record<MemoryType, string> = {
  FACT: "Hecho",
  PREFERENCE: "Preferencia",
  GOAL: "Meta",
  INSTRUCTION: "Instrucción",
  EPISODE: "Episodio",
};

const TYPE_COLOR: Record<MemoryType, string> = {
  FACT: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  PREFERENCE: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  GOAL: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  INSTRUCTION: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  EPISODE: "text-slate-400 bg-slate-400/10 border-slate-400/30",
};

export function MemoryCard({ memory }: MemoryCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memory.content);
  const updateMutation = useUpdateMemory();
  const deleteMutation = useDeleteMemory();
  const confirm = useConfirm();

  function save() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === memory.content) {
      setEditing(false);
      setDraft(memory.content);
      return;
    }
    updateMutation.mutate(
      { id: memory.id, input: { content: trimmed } },
      {
        onSuccess: () => setEditing(false),
      },
    );
  }

  function cancel() {
    setEditing(false);
    setDraft(memory.content);
  }

  async function onDelete() {
    const ok = await confirm({
      title: "Eliminar memoria",
      message: "Esta acción no se puede deshacer. La memoria se moverá al historial de eliminadas.",
      confirmText: "Eliminar",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    deleteMutation.mutate(memory.id);
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-colors hover:border-[var(--color-border-strong)]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
              TYPE_COLOR[memory.type],
            )}
          >
            {TYPE_LABEL[memory.type]}
          </span>
          <span className="text-xs text-[var(--color-subtle)]">
            {formatRelativeDate(memory.updated_at)}
          </span>
        </div>

        {!editing && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
              aria-label="Editar"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              disabled={deleteMutation.isPending}
              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)] disabled:opacity-50"
              aria-label="Eliminar"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="mt-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-foreground)] focus:border-[var(--color-primary)] focus:outline-none"
          />
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={cancel}>
              <X className="h-3.5 w-3.5" />
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={save}
              disabled={updateMutation.isPending}
            >
              <Check className="h-3.5 w-3.5" />
              Guardar
            </Button>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-[var(--color-foreground)]">
          {memory.content}
        </p>
      )}

      <div className="mt-3 flex items-center gap-4 text-[11px] text-[var(--color-subtle)]">
        <span>Importancia {(memory.importance * 100).toFixed(0)}%</span>
        <span>Confianza {(memory.confidence * 100).toFixed(0)}%</span>
        <span>Usos {memory.usage_count}</span>
        <span className="ml-auto uppercase">{memory.source}</span>
      </div>
    </div>
  );
}