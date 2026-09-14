"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUploadFile } from "@/lib/hooks/use-files";

const ACCEPTED_MIMES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
];

const ACCEPT_ATTR = ".pdf,.docx,.xlsx,.txt,.md,.csv,.json";

export function FileUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadFile();

  function onFiles(files: FileList | null) {
    setError(null);
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!ACCEPTED_MIMES.includes(file.type)) {
      setError(`Tipo no soportado: ${file.type || "desconocido"}`);
      return;
    }
    upload.mutate(file);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed",
          "px-6 py-12 text-center transition-colors",
          dragging
            ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
            : "border-[var(--color-border-strong)] hover:border-[var(--color-primary)] hover:bg-[var(--color-surface)]",
          upload.isPending && "pointer-events-none opacity-60",
        )}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-[var(--color-primary)]">
          <UploadCloud className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-medium">
            {upload.isPending
              ? "Subiendo…"
              : "Arrastra un archivo o haz click para subir"}
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            PDF, DOCX, XLSX, TXT, MD, CSV, JSON · máx. 25 MB
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="hidden"
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {error && (
        <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>
      )}
    </div>
  );
}