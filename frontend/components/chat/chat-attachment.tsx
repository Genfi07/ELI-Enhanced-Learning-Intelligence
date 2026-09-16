"use client";

import {
  FileText,
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Attachment } from "@/lib/hooks/use-attachment";

interface ChatAttachmentProps {
  attachment: Attachment;
  onRemove: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ChatAttachment({ attachment, onRemove }: ChatAttachmentProps) {
  const { status, fileName, sizeBytes, error, chunkCount } = attachment;

  return (
    <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2">
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
          status === "ready" && "bg-[var(--color-success)]/10 text-[var(--color-success)]",
          status === "failed" && "bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
          (status === "uploading" || status === "processing") &&
            "bg-[var(--color-primary-soft)] text-[var(--color-primary)]",
        )}
      >
        <FileText className="h-4 w-4" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{fileName}</p>
          <span className="shrink-0 text-[11px] text-[var(--color-subtle)]">
            formatBytes(attachment.sizeBytes ?? 0)
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px]">
          {status === "uploading" && (
            <>
              <Loader2 className="h-3 w-3 animate-spin text-[var(--color-primary)]" />
              <span className="text-[var(--color-muted)]">Subiendo…</span>
            </>
          )}
          {status === "processing" && (
            <>
              <Loader2 className="h-3 w-3 animate-spin text-[var(--color-primary)]" />
              <span className="text-[var(--color-muted)]">
                Procesando archivo…
              </span>
            </>
          )}
          {status === "ready" && (
            <>
              <CheckCircle2 className="h-3 w-3 text-[var(--color-success)]" />
              <span className="text-[var(--color-success)]">
                Listo{chunkCount ? ` · ${chunkCount} fragmentos` : ""}
              </span>
            </>
          )}
          {status === "failed" && (
            <>
              <AlertCircle className="h-3 w-3 text-[var(--color-danger)]" />
              <span className="truncate text-[var(--color-danger)]">
                {error || "Error"}
              </span>
            </>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={onRemove}
        className="shrink-0 rounded p-1 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
        aria-label="Quitar adjunto"
        title="Quitar adjunto"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}