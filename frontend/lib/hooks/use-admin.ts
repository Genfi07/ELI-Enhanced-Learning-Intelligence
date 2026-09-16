"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api/client";
export type { SettingItem, GuideEntry } from "@/lib/api/types";
import type {
  AdminConversation,
  AdminDocument,
  AdminMemory,
  AdminMessage,
  AdminUser,
  AdminUserDetail,
  AdminUserStats,
  AnalyticsOverview,
  AuditLogEntry,
  GuideEntry,
  SettingItem,
  SystemHealth,
  Timeseries,
} from "@/lib/api/types";

// =========================================================================== //
// Dashboard / Analytics
// =========================================================================== //
export function useAnalyticsOverview() {
  return useQuery<AnalyticsOverview>({
    queryKey: ["admin", "overview"],
    queryFn: () => apiGet<AnalyticsOverview>("/admin/analytics/overview"),
    staleTime: 30_000,
  });
}

export function useTimeseries(days = 7) {
  return useQuery<Timeseries>({
    queryKey: ["admin", "timeseries", days],
    queryFn: () =>
      apiGet<Timeseries>(`/admin/analytics/timeseries?days=${days}`),
    staleTime: 60_000,
  });
}

export function useSystemHealth() {
  return useQuery<SystemHealth>({
    queryKey: ["admin", "health"],
    queryFn: () => apiGet<SystemHealth>("/admin/system/health"),
    staleTime: 30_000,
  });
}

export function useAuditLogs(limit = 10) {
  return useQuery<AuditLogEntry[]>({
    queryKey: ["admin", "audit", limit],
    queryFn: () =>
      apiGet<AuditLogEntry[]>(`/admin/audit?limit=${limit}`),
    staleTime: 30_000,
  });
}

// =========================================================================== //
// Users
// =========================================================================== //
export function useAdminUsers(search?: string) {
  return useQuery<AdminUser[]>({
    queryKey: ["admin", "users", search ?? ""],
    queryFn: () => {
      const q = search ? `?search=${encodeURIComponent(search)}` : "";
      return apiGet<AdminUser[]>(`/admin/users${q}`);
    },
    staleTime: 20_000,
  });
}

export function useBlockUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; reason?: string }) =>
      apiPost<AdminUser>(`/admin/users/${args.id}/block`, {
        reason: args.reason ?? null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success("Usuario bloqueado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUnblockUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<AdminUser>(`/admin/users/${id}/unblock`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success("Usuario desbloqueado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useChangeUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; role: string }) =>
      apiPatch<AdminUser>(`/admin/users/${args.id}/role`, { role: args.role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success("Rol actualizado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/admin/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success("Usuario eliminado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export interface CreateUserInput {
  name: string;
  email: string;
  password: string;
  role: "USER" | "MODERATOR" | "ADMIN" | "SUPER_ADMIN";
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateUserInput) =>
      apiPost<AdminUser>("/admin/users", input),
    onSuccess: (user) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`Usuario "${user.name}" creado`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function usePromoteToSuper() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<AdminUser>(`/admin/users/${id}/promote`, { confirm: true }),
    onSuccess: (user) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`${user.name} ahora es SUPER_ADMIN`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// =========================================================================== //
// Config
// =========================================================================== //
export function useSettings() {
  return useQuery<SettingItem[]>({
    queryKey: ["admin", "config"],
    queryFn: () => apiGet<SettingItem[]>("/admin/config"),
    staleTime: 30_000,
  });
}

export function useUpdateSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { key: string; value: unknown }) =>
      apiPut<SettingItem>(`/admin/config/${args.key}`, { value: args.value }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "config"] });
      toast.success("Configuración actualizada");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => apiDelete(`/admin/config/${key}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "config"] });
      toast.success("Override eliminado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useResetAllSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ deleted: number }>("/admin/settings/reset-all", {}),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["admin", "config"] });
      toast.success(
        res.deleted === 0
          ? "No había overrides que eliminar"
          : `${res.deleted} override${res.deleted === 1 ? "" : "s"} eliminado${res.deleted === 1 ? "" : "s"}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useConfigGuide() {
  return useQuery<GuideEntry[]>({
    queryKey: ["admin", "config", "guide"],
    queryFn: () => apiGet<GuideEntry[]>("/admin/config/guide"),
    staleTime: 5 * 60_000,
  });
}

// =========================================================================== //
// A2 — Conversaciones y stats
// =========================================================================== //
export function useAllConversations(
  opts: { userId?: string; search?: string; limit?: number } = {},
) {
  return useQuery<AdminConversation[]>({
    queryKey: [
      "admin",
      "conversations",
      opts.userId ?? "",
      opts.search ?? "",
      opts.limit ?? 50,
    ],
    queryFn: () => {
      const params = new URLSearchParams();
      if (opts.userId) params.set("user_id", opts.userId);
      if (opts.search) params.set("search", opts.search);
      params.set("limit", String(opts.limit ?? 50));
      return apiGet<AdminConversation[]>(
        `/admin/conversations?${params.toString()}`,
      );
    },
    staleTime: 15_000,
  });
}

export function useUserConversations(userId: string | undefined) {
  return useQuery<AdminConversation[]>({
    queryKey: ["admin", "users", userId, "conversations"],
    enabled: !!userId,
    queryFn: () =>
      apiGet<AdminConversation[]>(
        `/admin/users/${userId}/conversations?limit=50`,
      ),
    staleTime: 15_000,
  });
}

export function useUserDetail(userId: string | undefined) {
  return useQuery<AdminUserDetail>({
    queryKey: ["admin", "users", userId, "detail"],
    enabled: !!userId,
    queryFn: () => apiGet<AdminUserDetail>(`/admin/users/${userId}/detail`),
    staleTime: 15_000,
  });
}

export function useConversationMessages(conversationId: string | undefined) {
  return useQuery<AdminMessage[]>({
    queryKey: ["admin", "conversations", conversationId, "messages"],
    enabled: !!conversationId,
    queryFn: () =>
      apiGet<AdminMessage[]>(
        `/admin/conversations/${conversationId}/messages?limit=500`,
      ),
    staleTime: 60_000,
  });
}

// Silenciar el warning de imports no usados (los tipos se usan en JSX externo)
export type {
  AdminConversation,
  AdminDocument,
  AdminMemory,
  AdminMessage,
  AdminUser,
  AdminUserDetail,
  AdminUserStats,
};