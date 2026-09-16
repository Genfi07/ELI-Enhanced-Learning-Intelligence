"use client";

import { create } from "zustand";

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
}

interface ConfirmState {
  isOpen: boolean;
  options: ConfirmOptions | null;
  resolver: ((ok: boolean) => void) | null;
  open: (opts: ConfirmOptions) => Promise<boolean>;
  close: (ok: boolean) => void;
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  isOpen: false,
  options: null,
  resolver: null,
  open: (opts) =>
    new Promise<boolean>((resolve) => {
      set({ isOpen: true, options: opts, resolver: resolve });
    }),
  close: (ok) => {
    const r = get().resolver;
    set({ isOpen: false, options: null, resolver: null });
    r?.(ok);
  },
}));

export function useConfirm() {
  return useConfirmStore((s) => s.open);
}