"use client";

import {
  FileText,
  FileSpreadsheet,
  FileCode,
  Trash2,
  RotateCw,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
} from "lucide-react";
import { cn, formatBytes, formatRelativeDate } from "@/lib/utils";
import type { Document, DocumentStatus } from "@/lib/api/types";
import {
  useDeleteFile,
  useReprocessFile,
} from "@/lib/hooks/use-files";

interface FileRowProps {
  doc: Document;
}

function iconFor(mime: string) {
  if (mime.includes("spreadsheet") || mime.includes("excel")) {
    return FileSpreadsheet;
  }
  if (mime.includes("json") || mime.includes("csv")) {
    return FileCode;
  }
  return FileText;
}

const STATUS_LABEL: Record<DocumentStatus, string> = {
  PENDING: "En cola",
  PROCESSING: "Procesando",
  READY: "Listo",
  FAILED: "Error",
};

function StatusPill({ status }: { status: DocumentStatus }) {
  const config: Record<
    DocumentStatus,
    { icon: React.ElementType; className: string }
  > = {
    PENDING: {
      icon: Clock,
      className: "text-[var(--color-muted)] bg-[var(--color-surface-hover)]",
    },
    PROCESSING: {
      icon: Loader2,
      className:
        "text-[var(--color-primary)] bg-[var(--color-primary-soft)] animate-pulse",
    },
    READY: {
      icon: CheckCircle2,
      className:
        "text-[var(--color-success)] bg-[var(--color-success)]/10",
    },
    FAILED: {
      icon: AlertCircle,
      className: "text-[var(--color-danger)] bg-[var(--color-danger)]/10",
    },
  };
  const { icon: Icon, className } = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-medium",
        className,
      )}
    >
      <Icon
        className={cn("h-3 w-3", status === "PROCESSING" && "animate-spin")}
      />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function FileRow({ doc }: FileRowProps) {
  const Icon = iconFor(doc.mime_type);
  const deleteMutation = useDeleteFile();
  const reprocessMutation = useReprocessFile();

  function onDelete() {
    if (!confirm(`¿Eliminar "${doc.title}"?`)) return;
    deleteMutation.mutate(doc.id);
  }

  function onReprocess() {
    reprocessMutation.mutate(doc.id);
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-colors hover:border-[var(--color-border-strong)]">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[var(--color-surface-hover)] text-[var(--color-muted)]">
        <Icon className="h-5 w-5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{doc.title}</p>
          <StatusPill status={doc.status} />
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-xs text-[var(--color-subtle)]">
          <span>{formatBytes(doc.size_bytes)}</span>
          {doc.status === "READY" && (
            <span>{doc.chunk_count} fragmentos</span>
          )}
          <span>{formatRelativeDate(doc.created_at)}</span>
        </div>
        {doc.status === "FAILED" && doc.error && (
          <p className="mt-1 line-clamp-2 text-xs text-[var(--color-danger)]">
            {doc.error}
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {doc.status === "FAILED" && (
          <button
            type="button"
            onClick={onReprocess}
            disabled={reprocessMutation.isPending}
            className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] disabled:opacity-50"
            aria-label="Reprocesar"
            title="Reprocesar"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={onDelete}
          disabled={deleteMutation.isPending}
          className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)] disabled:opacity-50"
          aria-label="Eliminar"
          title="Eliminar"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}