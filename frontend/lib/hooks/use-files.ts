"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost, apiUpload } from "@/lib/api/client";
import type { Document } from "@/lib/api/types";

export function useFiles() {
  return useQuery<Document[]>({
    queryKey: ["files"],
    queryFn: () => apiGet<Document[]>("/documents"),
    staleTime: 15_000,
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<Document>("/documents/upload", file),
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success(`"${doc.title}" subido`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/documents/${id}`),
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
    mutationFn: (id: string) => apiPost(`/documents/${id}/hide`),
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
    mutationFn: (id: string) => apiPost(`/documents/${id}/reprocess`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files"] });
      toast.success("Reprocesando archivo");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}