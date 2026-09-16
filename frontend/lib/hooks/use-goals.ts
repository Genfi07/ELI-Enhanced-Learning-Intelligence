"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api/client";
import type { Goal, GoalKind, GoalStatus } from "@/lib/api/types";

export function useGoals(status?: GoalStatus) {
  return useQuery<Goal[]>({
    queryKey: ["goals", status ?? "all"],
    queryFn: () => {
      const q = status ? `?status=${status}` : "";
      return apiGet<Goal[]>(`/goals${q}`);
    },
    staleTime: 30_000,
  });
}

export function useCreateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      kind: GoalKind;
      content: string;
      priority?: number;
    }) => apiPost<Goal>("/goals", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      toast.success("Meta creada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; input: Partial<Goal> }) =>
      apiPatch<Goal>(`/goals/${args.id}`, args.input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useAbandonGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/goals/${id}/abandon`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      toast.success("Meta abandonada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/goals/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      toast.success("Meta eliminada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}