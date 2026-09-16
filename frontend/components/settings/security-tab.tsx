"use client";

import { useState } from "react";
import { KeyRound, LogOut, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useChangePassword,
  useLogoutAll,
} from "@/lib/hooks/use-settings";
import { useConfirm } from "@/lib/stores/confirm-store";

export function SecurityTab() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const changePwd = useChangePassword();
  const logoutAll = useLogoutAll();
  const confirmModal = useConfirm();

  const canSubmit =
    current.length >= 8 &&
    next.length >= 8 &&
    next === confirm &&
    next !== current &&
    !changePwd.isPending;

  function submit() {
    if (!canSubmit) return;
    changePwd.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setConfirm("");
        },
      },
    );
  }

  async function handleLogoutAll() {
    const ok = await confirmModal({
      title: "Cerrar todas las sesiones",
      message:
        "Se cerrará la sesión en TODOS los dispositivos, incluido este. Tendrás que volver a entrar.",
      confirmText: "Cerrar todas",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    logoutAll.mutate();
  }

  return (
    <form
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="space-y-6"
    >
      {/* Cambiar contraseña */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <header className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="text-sm font-semibold">Cambiar contraseña</h2>
        </header>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Al cambiarla, se cerrarán todas tus sesiones excepto esta.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Contraseña actual
            </label>
            <Input
              type="password"
              name="eli-current-password"
              autoComplete="off"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Nueva contraseña
            </label>
            <Input
              type="password"
              name="eli-new-password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="mt-1"
            />
            <p className="mt-1 text-[11px] text-[var(--color-subtle)]">
              Mínimo 8 caracteres.
            </p>
          </div>
          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Confirmar nueva
            </label>
            <Input
              type="password"
              name="eli-confirm-password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="mt-1"
            />
            {confirm.length > 0 && confirm !== next && (
              <p className="mt-1 text-[11px] text-[var(--color-danger)]">
                Las contraseñas no coinciden.
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <Button
            type="submit"
            size="sm"
            disabled={!canSubmit}
          >
            {changePwd.isPending ? "Cambiando…" : "Cambiar contraseña"}
          </Button>
        </div>
      </section>

      {/* Conexiones externas */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <header className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="text-sm font-semibold">Conexiones externas</h2>
        </header>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Conecta tu cuenta de Google para iniciar sesión sin contraseña.
        </p>
        <div className="mt-4">
          <a
            href="/api/v1/auth/google/start"
            className="inline-flex items-center gap-2 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--color-surface-hover)]"
          >
            <Link2 className="h-3.5 w-3.5" />
            Conectar con Google
          </a>
        </div>
      </section>

      {/* Sesiones */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <header className="flex items-center gap-2">
          <LogOut className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="text-sm font-semibold">Sesiones activas</h2>
        </header>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Cierra la sesión en todos los dispositivos donde tengas ELI abierto.
        </p>
        <div className="mt-4 flex justify-end">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleLogoutAll}
            disabled={logoutAll.isPending}
          >
            <LogOut className="h-3.5 w-3.5" />
            {logoutAll.isPending ? "Cerrando…" : "Cerrar todas las sesiones"}
          </Button>
        </div>
      </section>
    </form>
  );
}