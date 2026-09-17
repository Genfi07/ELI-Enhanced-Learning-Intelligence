"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost, apiUpload } from "@/lib/api/client";
import type { Document } from "@/lib/api/types";

/**
 * Lista de documentos del usuario.
 * Usa ?state=all para incluir activos, eliminados y ocultos.
 * El backend excluye de "active" los docs cuyo archivo físico ya se borró
 * tras la ingesta (physical_deleted_at), pero el texto sigue disponible.
 */
export function useFiles() {
  return useQuery<Document[]>({
    queryKey: ["files"],
    queryFn: () => apiGet<Document[]>("/files?state=all"),
    staleTime: 15_000,
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<Document>("/files", file),
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ["files"] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
      toast.success(`"${doc.title}" subido`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/files/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success("Archivo eliminado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useHideFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/files/${id}/hide`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success("Archivo oculto");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useReprocessFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/files/${id}/reprocess`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success("Reprocesando archivo");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}