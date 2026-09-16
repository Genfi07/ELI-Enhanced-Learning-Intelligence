"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api/client";
import type { Tool, ToolInvokeResult } from "@/lib/api/types";

export interface ToolCallRecord {
  id: string;
  tool_name: string;
  status: string;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
  autonomy_level: number;
  latency_ms: number;
  created_at: string;
}

export function useTools() {
  return useQuery<Tool[]>({
    queryKey: ["tools"],
    queryFn: () => apiGet<Tool[]>("/tools"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useToolCalls(limit = 20) {
  return useQuery<ToolCallRecord[]>({
    queryKey: ["toolCalls", limit],
    queryFn: () => apiGet<ToolCallRecord[]>(`/tools/calls?limit=${limit}`),
    staleTime: 10_000,
  });
}

export function useInvokeTool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      name: string;
      arguments: Record<string, unknown>;
    }) =>
      apiPost<ToolInvokeResult>(`/tools/${args.name}/invoke`, {
        arguments: args.arguments,
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["toolCalls"] });
      if (result.status === "OK") {
        toast.success(`${result.tool_name} · ${result.latency_ms} ms`);
      } else if (result.status === "PENDING_CONFIRMATION") {
        toast.info("Acción pendiente de confirmación");
      } else {
        toast.error(result.error || `Estado: ${result.status}`);
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });
}