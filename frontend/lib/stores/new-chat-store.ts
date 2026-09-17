"use client";

import { create } from "zustand";

/**
 * Coordinación entre la barra lateral y la vista del chat.
 *
 * - `key` se incrementa al pulsar "Nuevo chat" → fuerza remount de ChatView
 *   aunque ya estés en /chat (un Link normal no resetearía el estado).
 * - `pendingPrompt` permite precargar el composer desde /tools (flujos).
 * - `activeConversationId` mantiene sincronizado el chat activo sin depender
 *   de la URL. Así evitamos que Next.js remonte el ChatView cuando el backend
 *   crea una nueva conversación.
 */
interface NewChatState {
  key: number;
  pendingPrompt: string | null;
  activeConversationId: string | null;
  bump: () => void;
  prefill: (prompt: string) => void;
  consumePrompt: () => string | null;
  setActiveConversationId: (id: string | null) => void;
}

export const useNewChatStore = create<NewChatState>((set, get) => ({
  key: 0,
  pendingPrompt: null,
  activeConversationId: null,
  bump: () =>
    set((s) => ({
      key: s.key + 1,
      pendingPrompt: null,
      activeConversationId: null,
    })),
  prefill: (prompt: string) =>
    set((s) => ({ key: s.key + 1, pendingPrompt: prompt })),
  consumePrompt: () => {
    const p = get().pendingPrompt;
    if (p !== null) set({ pendingPrompt: null });
    return p;
  },
  setActiveConversationId: (id) => set({ activeConversationId: id }),
}));