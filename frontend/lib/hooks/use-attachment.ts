"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiUpload } from "@/lib/api/client";
import type { Document } from "@/lib/api/types";

// --------------------------------------------------------------------------- //
// MIME types aceptados
// --------------------------------------------------------------------------- //
export const ACCEPTED_MIMES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "image/heic",
];

export const ACCEPTED_ATTR =
  ".pdf,.docx,.xlsx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp,.gif,.heic";

// --------------------------------------------------------------------------- //
// Tipos
// --------------------------------------------------------------------------- //
export type AttachmentStatus =
  | "uploading"
  | "processing"
  | "ready"
  | "failed";

export interface Attachment {
  id: string;
  fileName: string;
  sizeBytes?: number;
  status: AttachmentStatus;
  docId?: string;
  chunkCount?: number;
  error?: string;
}

// --------------------------------------------------------------------------- //
// Hook
// --------------------------------------------------------------------------- //
export function useAttachment() {
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const clear = useCallback(() => {
    stopPolling();
    setAttachment(null);
  }, [stopPolling]);

  // Cleanup al desmontar
  useEffect(() => stopPolling, [stopPolling]);

  const attach = useCallback(
    async (file: File) => {
      // Solo un archivo a la vez
      if (attachment) return;

      // Validar mime
      if (!ACCEPTED_MIMES.includes(file.type)) {
        setAttachment({
          id: "err",
          fileName: file.name,
          status: "failed",
          error: `Tipo no soportado: ${file.type || "desconocido"}`,
        });
        return;
      }

      const tempId = `${Date.now()}-${file.name}`;
           setAttachment({
        id: tempId,
        fileName: file.name,
        sizeBytes: file.size,
        status: "uploading",
      });

      try {
        const doc = await apiUpload<Document>("/files", file);

        setAttachment({
          id: tempId,
          fileName: file.name,
          status: doc.status === "READY" ? "ready" : "processing",
          docId: doc.id,
          chunkCount: doc.chunk_count,
        });

        // Si no está listo todavía, hacemos polling cada 1.5s
        if (doc.status !== "READY" && doc.status !== "FAILED") {
          stopPolling();
          pollRef.current = window.setInterval(async () => {
            try {
              const d = await apiGet<Document>(`/files/${doc.id}`);
              if (d.status === "READY") {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? {
                        ...prev,
                        status: "ready",
                        chunkCount: d.chunk_count,
                      }
                    : null,
                );
              } else if (d.status === "FAILED") {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? {
                        ...prev,
                        status: "failed",
                        error: "El documento no se pudo procesar",
                      }
                    : null,
                );
              }
            } catch {
              stopPolling();
            }
          }, 1500);
        }
      } catch (err) {
        setAttachment({
          id: tempId,
          fileName: file.name,
          status: "failed",
          error: (err as Error).message,
        });
      }
    },
    [attachment, stopPolling],
  );

  return { attachment, attach, clear };
}