"use client";

import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { Sidebar } from "@/components/layout/sidebar";

/**
 * Layout protegido de la app.
 *
 * Todas las rutas dentro del route group `(app)` comparten esta shell:
 * sidebar + contenido. El middleware garantiza que solo llegan usuarios
 * con cookie de sesión; aquí solo esperamos a que el user cargue desde
 * /auth/me para pasárselo al sidebar.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-[var(--color-muted)]">
        Cargando…
      </div>
    );
  }

  if (isError || !user) {
    // El middleware debería haber redirigido. Si llegamos aquí, es un caso
    // raro (cookie revocada en backend sin que el navegador lo sepa).
    // Forzamos reload para que el middleware re-evalúe.
    if (typeof window !== "undefined") window.location.href = "/login";
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar user={user} />
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}