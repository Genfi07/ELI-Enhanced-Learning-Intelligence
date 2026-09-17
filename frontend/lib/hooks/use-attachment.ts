"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiUpload } from "@/lib/api/client";
import { HttpError } from "@/lib/api/client";
import type { Document } from "@/lib/api/types";

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

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_FAILURES = 10; // tolera 10 fallos seguidos antes de rendirse

export function useAttachment() {
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const pollRef = useRef<number | null>(null);
  const failuresRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    failuresRef.current = 0;
  }, []);

  const clear = useCallback(() => {
    stopPolling();
    setAttachment(null);
  }, [stopPolling]);

  useEffect(() => stopPolling, [stopPolling]);

  const attach = useCallback(
    async (file: File) => {
      if (attachment) return;

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
          sizeBytes: file.size,
          status: doc.status === "READY" ? "ready" : "processing",
          docId: doc.id,
          chunkCount: doc.chunk_count,
        });

        if (doc.status !== "READY" && doc.status !== "FAILED") {
          stopPolling();
          failuresRef.current = 0;

          pollRef.current = window.setInterval(async () => {
            try {
              const d = await apiGet<Document>(`/files/${doc.id}`);
              failuresRef.current = 0; // reset en éxito

              if (d.status === "READY") {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? { ...prev, status: "ready", chunkCount: d.chunk_count }
                    : null,
                );
              } else if (d.status === "FAILED") {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? {
                        ...prev,
                        status: "failed",
                        error: d.error || "El documento no se pudo procesar",
                      }
                    : null,
                );
              }
            } catch (err) {
              failuresRef.current += 1;

              // 404 → el documento no existe, detener.
              if (err instanceof HttpError && err.status === 404) {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? { ...prev, status: "failed", error: "Documento no encontrado" }
                    : null,
                );
                return;
              }

              // Cualquier otro error (429, 500, red, cold start) →
              // seguir intentando hasta POLL_MAX_FAILURES.
              if (failuresRef.current >= POLL_MAX_FAILURES) {
                stopPolling();
                setAttachment((prev) =>
                  prev
                    ? {
                        ...prev,
                        status: "failed",
                        error: "No se pudo verificar el estado del archivo",
                      }
                    : null,
                );
              }
            }
          }, POLL_INTERVAL_MS);
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