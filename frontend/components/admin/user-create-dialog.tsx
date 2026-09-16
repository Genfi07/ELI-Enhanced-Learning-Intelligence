"use client";

import { useState } from "react";
import { X, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateUser } from "@/lib/hooks/use-admin";
import { cn } from "@/lib/utils";

interface UserCreateDialogProps {
  open: boolean;
  onClose: () => void;
  /** El rol máximo que el actor puede crear. Si el actor es ADMIN,
   *  no podrá crear SUPER_ADMIN. Si es SUPER_ADMIN, podrá todo. */
  isSuperAdmin: boolean;
}

const ROLES = ["USER", "MODERATOR", "ADMIN", "SUPER_ADMIN"] as const;

export function UserCreateDialog({
  open,
  onClose,
  isSuperAdmin,
}: UserCreateDialogProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("USER");
  const createMutation = useCreateUser();

  if (!open) return null;

  const availableRoles = isSuperAdmin
    ? ROLES
    : (["USER", "MODERATOR", "ADMIN"] as const);

  const canSubmit =
    name.trim().length > 0 &&
    email.trim().length > 3 &&
    password.length >= 8 &&
    !createMutation.isPending;

  function submit() {
    if (!canSubmit) return;
    createMutation.mutate(
      {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        role,
      },
      {
        onSuccess: () => {
          setName("");
          setEmail("");
          setPassword("");
          setRole("USER");
          onClose();
        },
      },
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative z-10 w-full max-w-md rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] p-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
              <UserPlus className="h-4 w-4" />
            </div>
            <h2 className="text-base font-semibold tracking-tight">
              Nuevo usuario
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-5">
          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Nombre
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Juan Pérez"
              autoFocus
            />
          </div>

          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Email
            </label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="juan@ejemplo.com"
            />
          </div>

          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Contraseña temporal
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mínimo 8 caracteres"
            />
            <p className="mt-1 text-[11px] text-[var(--color-subtle)]">
              Compártela con el usuario para que pueda entrar y cambiarla.
            </p>
          </div>

          <div>
            <label className="text-xs text-[var(--color-subtle)]">Rol</label>
            <select
              value={role}
              onChange={(e) =>
                setRole(e.target.value as (typeof ROLES)[number])
              }
              className={cn(
                "mt-1 w-full rounded-md border border-[var(--color-border-strong)]",
                "bg-[var(--color-surface)] px-3 py-2 text-sm",
                "focus:border-[var(--color-primary)] focus:outline-none",
              )}
            >
              {availableRoles.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            {!isSuperAdmin && (
              <p className="mt-1 text-[11px] text-[var(--color-subtle)]">
                Solo un SUPER_ADMIN puede crear otros SUPER_ADMIN.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] p-4">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {createMutation.isPending ? "Creando…" : "Crear usuario"}
          </Button>
        </div>
      </div>
    </div>
  );
}