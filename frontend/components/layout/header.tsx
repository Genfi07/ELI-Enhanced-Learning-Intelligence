"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api/client";
import { useAuthStore } from "@/lib/stores/auth-store";
import type { User } from "@/lib/api/types";

interface HeaderProps {
  title?: string;
  user: User;
}

export function Header({ title, user }: HeaderProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clear = useAuthStore((s) => s.clear);
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onLogout() {
    setBusy(true);
    try {
      await apiPost("/auth/logout");
    } catch {
      // Aunque falle, limpiamos el cliente.
    }
    queryClient.clear();
    clear();
    toast.success("Sesión cerrada");
    router.replace("/login");
    router.refresh();
  }

  return (
   <header className="surface-glass flex h-12 shrink-0 items-center justify-between border-b px-3 transition-soft md:h-14 md:px-6">
      <div className="truncate text-sm text-[var(--color-muted)]">
        {title ?? ""}
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-[var(--color-surface-hover)]"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-xs font-medium text-[var(--color-primary)]">
            {user.name.charAt(0).toUpperCase()}
          </div>
          <span className="hidden text-[var(--color-muted)] sm:inline">
            {user.name}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-[var(--color-subtle)]" />
        </button>

        {menuOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute right-0 top-full z-20 mt-1 w-56 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-xl">
              <div className="border-b border-[var(--color-border)] px-3 py-2">
                <p className="text-sm font-medium">{user.name}</p>
                <p className="truncate text-xs text-[var(--color-muted)]">
                  {user.email}
                </p>
                <p className="mt-1 text-[10px] uppercase tracking-wider text-[var(--color-subtle)]">
                  {user.role}
                </p>
              </div>
              <button
                type="button"
                onClick={onLogout}
                disabled={busy}
                className="mt-1 flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-[var(--color-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] disabled:opacity-50"
              >
                <LogOut className="h-3.5 w-3.5" />
                {busy ? "Saliendo…" : "Cerrar sesión"}
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
}