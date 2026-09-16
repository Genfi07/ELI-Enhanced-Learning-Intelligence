"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

/**
 * Devuelve el usuario autenticado actual.
 *
 * - staleTime alto (5 min): el usuario no cambia frecuentemente.
 * - Si el backend devuelve 401, React Query lo marca como error y
 *   `data` queda undefined. Los componentes que lo usan deben
 *   manejar ese estado (el layout suele redirigir a /login).
 */
export function useCurrentUser() {
  return useQuery<User>({
    queryKey: ["current-user"],
    queryFn: () => apiGet<User>("/auth/me"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}