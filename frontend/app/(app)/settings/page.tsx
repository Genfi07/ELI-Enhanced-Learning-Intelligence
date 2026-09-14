"use client";

import { useState } from "react";
import { User, Shield, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useAuthStore } from "@/lib/stores/auth-store";
import { apiPost } from "@/lib/api/client";
import { cn } from "@/lib/utils";

const AUTONOMY_LEVELS = [
  {
    level: 0,
    title: "Solo conversación",
    description: "ELI no ejecuta ninguna herramienta, solo responde.",
  },
  {
    level: 1,
    title: "Lectura",
    description: "Puede consultar información sin modificar nada.",
  },
  {
    level: 2,
    title: "Herramientas internas",
    description: "Calculadora, fecha/hora y operaciones internas seguras.",
  },
  {
    level: 3,
    title: "Acciones externas reversibles",
    description: "Búsqueda web, descarga de URLs. Reversible.",
  },
  {
    level: 4,
    title: "Acciones sensibles",
    description: "Requieren confirmación explícita antes de ejecutarse.",
  },
];

export default function SettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const clear = useAuthStore((s) => s.clear);
  const [loggingOut, setLoggingOut] = useState(false);

  if (!user) return null;

  // El nivel de autonomía vive en preferences, no lo devuelve UserOut.
  // Lo mostramos como referencia según el rol (mismo cálculo que backend).
  const defaultAutonomy =
    user.role === "ADMIN" || user.role === "SUPER_ADMIN" ? 4 : 2;

  async function onLogout() {
    setLoggingOut(true);
    try {
      await apiPost("/auth/logout");
    } catch {
      // Ignorar
    }
    queryClient.clear();
    clear();
    toast.success("Sesión cerrada");
    router.replace("/login");
    router.refresh();
  }

  return (
    <>
      <Header title="Ajustes" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">Ajustes</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Tu perfil y preferencias de ELI.
          </p>

          {/* Perfil */}
          <section className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              <User className="h-3 w-3" />
              Perfil
            </h2>
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-base font-medium text-[var(--color-primary)]">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{user.name}</p>
                  <p className="truncate text-sm text-[var(--color-muted)]">
                    {user.email}
                  </p>
                </div>
                <span
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
                    user.role === "SUPER_ADMIN"
                      ? "bg-amber-500/10 text-amber-400"
                      : user.role === "ADMIN"
                        ? "bg-purple-500/10 text-purple-400"
                        : "bg-[var(--color-surface-hover)] text-[var(--color-muted)]",
                  )}
                >
                  {user.role}
                </span>
              </div>
            </div>
          </section>

          {/* Autonomía */}
          <section className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              <Shield className="h-3 w-3" />
              Nivel de autonomía
            </h2>
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <p className="text-sm text-[var(--color-muted)]">
                Qué acciones puede ejecutar ELI sin pedirte confirmación.
                Tu nivel actual es{" "}
                <strong className="text-[var(--color-foreground)]">
                  {defaultAutonomy}
                </strong>
                .
              </p>
              <div className="mt-4 space-y-2">
                {AUTONOMY_LEVELS.map((lvl) => {
                  const active = lvl.level === defaultAutonomy;
                  const disabled = lvl.level > defaultAutonomy;
                  return (
                    <div
                      key={lvl.level}
                      className={cn(
                        "flex items-start gap-3 rounded-md border p-3 transition-colors",
                        active
                          ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                          : "border-[var(--color-border)]",
                        disabled && "opacity-50",
                      )}
                    >
                      <div
                        className={cn(
                          "flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-medium",
                          active
                            ? "bg-[var(--color-primary)] text-white"
                            : "bg-[var(--color-surface-hover)] text-[var(--color-muted)]",
                        )}
                      >
                        {lvl.level}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{lvl.title}</p>
                        <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                          {lvl.description}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-xs text-[var(--color-subtle)]">
                El nivel de autonomía lo gestiona un administrador. Pídele que
                lo ajuste si necesitas más.
              </p>
            </div>
          </section>

          {/* Sesión */}
          <section className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              <LogOut className="h-3 w-3" />
              Sesión
            </h2>
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">Cerrar sesión</p>
                  <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                    Se revocará la sesión actual en el servidor.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  onClick={onLogout}
                  disabled={loggingOut}
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {loggingOut ? "Saliendo…" : "Cerrar sesión"}
                </Button>
              </div>
            </div>
          </section>

          <p className="mt-12 text-center text-xs text-[var(--color-subtle)]">
            ELI v0.1.0 · Fase 8 en construcción
          </p>
        </div>
      </main>
    </>
  );
}