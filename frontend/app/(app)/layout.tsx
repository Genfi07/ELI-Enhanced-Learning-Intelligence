"use client";

import { useState, useEffect } from "react";
import { Menu, X } from "lucide-react";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { Sidebar } from "@/components/layout/sidebar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: user, isLoading, isError } = useCurrentUser();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // iOS Safari no encoge el layout cuando aparece el teclado.
  // Usamos visualViewport para medir la altura real visible y aplicarla
  // como altura del contenedor principal. Así el input queda pegado al teclado.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const update = () => {
      document.documentElement.style.setProperty(
        "--app-height",
        `${vv.height}px`,
      );
    };
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    update();
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-[var(--color-muted)]">
        Cargando…
      </div>
    );
  }

  if (isError || !user) {
    if (typeof window !== "undefined") window.location.href = "/login";
    return null;
  }

  return (
    <div className="flex overflow-hidden"
      style={{ height: "var(--app-height, 100dvh)" }}>
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-300 ease-in-out",
          "md:relative md:w-64 md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="absolute right-3 top-3 z-50 rounded-full p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] md:hidden"
          aria-label="Cerrar menú"
        >
          <X className="h-5 w-5" />
        </button>

        <Sidebar user={user} onNavigate={() => setSidebarOpen(false)} />
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden min-h-0">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)]"
            aria-label="Abrir menú"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-primary)]/15 text-[var(--color-primary)]">
              <span className="text-xs font-bold">E</span>
            </div>
            <span className="text-sm font-semibold">ELI</span>
          </div>
        </header>

        <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
          {children}
        </div>
      </div>

      <ConfirmDialog />
    </div>
  );
}