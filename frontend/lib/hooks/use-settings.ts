"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api/client";

// --------------------------------------------------------------------------- //
// Tipos
// --------------------------------------------------------------------------- //
export interface Preferences {
  autonomy_level: number;
  response_style: "concise" | "balanced" | "detailed";
  language: string;
  theme: "dark" | "light" | "system";
  /** Calculado por el backend a partir del rol del usuario. */
  max_autonomy_level: number;
  /** Rol actual del usuario, devuelto por el backend. */
  role: string;
}

export interface UpdateProfileInput {
  name?: string;
  email?: string;
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}

// --------------------------------------------------------------------------- //
// Queries
// --------------------------------------------------------------------------- //
export function usePreferences() {
  return useQuery<Preferences>({
    queryKey: ["settings", "preferences"],
    queryFn: () => apiGet<Preferences>("/auth/me/preferences"),
    staleTime: 60_000,
  });
}

// --------------------------------------------------------------------------- //
// Mutations
// --------------------------------------------------------------------------- //
export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateProfileInput) => apiPatch("/auth/me", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      qc.invalidateQueries({ queryKey: ["current-user"] });
      toast.success("Perfil actualizado");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdatePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<Preferences>) =>
      apiPatch<Preferences>("/auth/me/preferences", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings", "preferences"] });
      toast.success("Preferencias guardadas");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (input: ChangePasswordInput) =>
      apiPost("/auth/me/change-password", input),
    onSuccess: () => toast.success("Contraseña actualizada"),
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useLogoutAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost("/auth/me/logout-all"),
    onSuccess: () => {
      qc.clear();
      toast.success("Todas las sesiones cerradas");
      window.location.href = "/login";
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteMyAccount() {
  return useMutation({
    mutationFn: (confirmEmail: string) =>
      apiDelete("/auth/me", { confirm_email: confirmEmail }),
    onSuccess: () => {
      toast.success("Cuenta eliminada");
      window.location.href = "/login";
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// --------------------------------------------------------------------------- //
// Exportar (descarga directa, sin React Query)
// --------------------------------------------------------------------------- //
export async function exportMyData(): Promise<void> {
  const data = await apiGet<Record<string, unknown>>("/auth/me/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `eli-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}