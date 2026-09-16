"use client";

import { create } from "zustand";
import type { User } from "@/lib/api/types";

/**
 * Estado de autenticación del usuario.
 *
 * Importante: la sesión real vive en una cookie httpOnly del backend.
 * Este store solo cachea los datos del usuario para que la UI pueda
 * renderizar sin esperar a cada fetch. Se hidrata desde useCurrentUser.
 *
 * Al hacer logout → clear() para limpiar la UI.
 */
interface AuthState {
  user: User | null;
  setUser: (user: User | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  clear: () => set({ user: null }),
}));