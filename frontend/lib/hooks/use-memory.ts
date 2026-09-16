"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api/client";
import type { Memory } from "@/lib/api/types";

export function useMemories(status?: string) {
  return useQuery<Memory[]>({
    queryKey: ["memories", status ?? "all"],
    queryFn: () => {
      const q = status ? `?status=${status}` : "";
      return apiGet<Memory[]>(`/memory${q}`);
    },
    staleTime: 30_000,
  });
}

export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { content: string; type?: string }) =>
      apiPost<Memory>("/memory", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      toast.success("Memoria creada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; input: Partial<Memory> }) =>
      apiPatch<Memory>(`/memory/${args.id}`, args.input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      toast.success("Memoria actualizada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/memory/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      toast.success("Memoria eliminada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRestoreMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/memory/${id}/restore`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      toast.success("Memoria restaurada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}