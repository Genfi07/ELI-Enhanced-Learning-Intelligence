"use client";

import {
  BookOpen,
  Compass,
  Sparkles,
  Heart,
  Lightbulb,
  Play,
  Pause,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { cn, formatRelativeDate } from "@/lib/utils";
import type { Goal, GoalKind, GoalStatus } from "@/lib/api/types";
import { useUpdateGoal, useAbandonGoal } from "@/lib/hooks/use-goals";
import { useConfirm } from "@/lib/stores/confirm-store";

interface GoalCardProps {
  goal: Goal;
  canEdit: boolean;
}

const KIND_META: Record<
  GoalKind,
  { label: string; Icon: React.ElementType; color: string }
> = {
  LEARN: {
    label: "Aprender",
    Icon: BookOpen,
    color: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  },
  EXPLORE: {
    label: "Explorar",
    Icon: Compass,
    color: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  },
  IMPROVE: {
    label: "Mejorar",
    Icon: Sparkles,
    color: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  },
  CONNECT: {
    label: "Conectar",
    Icon: Heart,
    color: "text-pink-400 bg-pink-400/10 border-pink-400/30",
  },
  PROPOSE: {
    label: "Proponer",
    Icon: Lightbulb,
    color: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  },
};

const ORIGIN_LABEL: Record<string, string> = {
  SELF: "Espontánea",
  TAUGHT: "Enseñada",
  DETECTED: "Detectada",
};

const STATUS_LABEL: Record<GoalStatus, string> = {
  ACTIVE: "Activa",
  PAUSED: "En pausa",
  ACHIEVED: "Cumplida",
  ABANDONED: "Abandonada",
};

export function GoalCard({ goal, canEdit }: GoalCardProps) {
  // Fallback por si el backend devuelve kind null/undefined
  const kind: GoalKind = (goal.kind ?? "LEARN") as GoalKind;
  const { label, Icon, color } = KIND_META[kind] ?? KIND_META.LEARN;

  const updateMutation = useUpdateGoal();
  const abandonMutation = useAbandonGoal();
  const confirm = useConfirm();

  function toggleStatus() {
    const newStatus: GoalStatus =
      goal.status === "ACTIVE" ? "PAUSED" : "ACTIVE";
    updateMutation.mutate({ id: goal.id, input: { status: newStatus } });
  }

  function markAchieved() {
    updateMutation.mutate({ id: goal.id, input: { status: "ACHIEVED" } });
  }

  async function onAbandon() {
    const ok = await confirm({
      title: "Abandonar meta",
      message: `¿Seguro que quieres abandonar "${goal.content}"? Podrás verla en el historial.`,
      confirmText: "Abandonar",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    abandonMutation.mutate(goal.id);
  }

  const isActive = goal.status === "ACTIVE";
  const isPaused = goal.status === "PAUSED";
  const isClosed = goal.status === "ACHIEVED" || goal.status === "ABANDONED";

  const originLabel = goal.origin
    ? (ORIGIN_LABEL[goal.origin] ?? goal.origin)
    : "—";

  const relatedTopics = goal.related_topics ?? [];
  const progressNotesCount = goal.progress_notes?.length ?? 0;

  return (
    <div
      className={cn(
        "rounded-lg border bg-[var(--color-surface)] p-4 transition-colors",
        isActive
          ? "border-[var(--color-border)]"
          : "border-[var(--color-border)] opacity-75",
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium",
            color,
          )}
        >
          <Icon className="h-3 w-3" />
          {label}
        </span>

        <span className="text-[11px] text-[var(--color-subtle)]">
          {originLabel}
        </span>

        {goal.priority != null && (
          <span className="text-[11px] text-[var(--color-subtle)]">
            · prioridad {goal.priority}
          </span>
        )}

        <span
          className={cn(
            "ml-auto rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
            isActive &&
              "bg-[var(--color-success)]/10 text-[var(--color-success)]",
            isPaused && "bg-amber-400/10 text-amber-400",
            goal.status === "ACHIEVED" &&
              "bg-[var(--color-primary)]/10 text-[var(--color-primary)]",
            goal.status === "ABANDONED" &&
              "bg-[var(--color-subtle)]/10 text-[var(--color-subtle)]",
          )}
        >
          {STATUS_LABEL[goal.status]}
        </span>
      </div>

      <p className="mt-2.5 text-sm leading-relaxed">{goal.content}</p>

      {relatedTopics.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {relatedTopics.map((t) => (
            <span
              key={t}
              className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 text-[10px] text-[var(--color-muted)]"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2 text-[11px] text-[var(--color-subtle)]">
        <span>
          {goal.achieved_at
            ? `Cumplida ${formatRelativeDate(goal.achieved_at)}`
            : goal.abandoned_at
              ? `Abandonada ${formatRelativeDate(goal.abandoned_at)}`
              : `Creada ${formatRelativeDate(goal.created_at)}`}
        </span>

        {progressNotesCount > 0 && (
          <span>· {progressNotesCount} nota(s)</span>
        )}

        {canEdit && !isClosed && (
          <div className="ml-auto flex gap-1">
            <button
              type="button"
              onClick={toggleStatus}
              disabled={updateMutation.isPending}
              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] disabled:opacity-50"
              title={isActive ? "Pausar" : "Reactivar"}
            >
              {isActive ? (
                <Pause className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
            </button>

            <button
              type="button"
              onClick={markAchieved}
              disabled={updateMutation.isPending}
              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-success)] disabled:opacity-50"
              title="Marcar cumplida"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
            </button>

            <button
              type="button"
              onClick={onAbandon}
              disabled={abandonMutation.isPending}
              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)] disabled:opacity-50"
              title="Abandonar"
            >
              <XCircle className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}