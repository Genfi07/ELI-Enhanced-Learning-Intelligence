"use client";

import { useEffect, useState } from "react";
import { Check, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useUpdateProfile } from "@/lib/hooks/use-settings";
import { formatRelativeDate } from "@/lib/utils";
import type { User } from "@/lib/api/types";

export function AccountTab({ user }: { user: User }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const update = useUpdateProfile();

  useEffect(() => {
    setName(user.name);
    setEmail(user.email);
  }, [user.name, user.email]);

  const dirty = name !== user.name || email !== user.email;

  function save() {
    update.mutate(
      {
        ...(name !== user.name ? { name } : {}),
        ...(email !== user.email ? { email } : {}),
      },
      { onSuccess: () => setEditing(false) },
    );
  }

  function cancel() {
    setName(user.name);
    setEmail(user.email);
    setEditing(false);
  }

  return (
    <div className="space-y-6">
      {/* Card de identidad */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-lg font-medium text-[var(--color-primary)]">
            {user.name.charAt(0).toUpperCase()}
          </div>

          <div className="min-w-0 flex-1 space-y-3">
            <div>
              <label className="text-xs text-[var(--color-subtle)]">
                Nombre
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={!editing}
                className="mt-1"
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
                disabled={!editing}
                className="mt-1"
              />
            </div>

            <div className="flex items-center gap-2 text-[11px] text-[var(--color-subtle)]">
              <span className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 uppercase tracking-wider">
                {user.role}
              </span>
              <span>
                Último acceso:{" "}
                {user.last_login_at
                  ? formatRelativeDate(user.last_login_at)
                  : "—"}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2 border-t border-[var(--color-border)] pt-4">
          {!editing ? (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="h-3.5 w-3.5" />
              Editar
            </Button>
          ) : (
            <>
              <Button variant="ghost" size="sm" onClick={cancel}>
                Cancelar
              </Button>
              <Button
                size="sm"
                onClick={save}
                disabled={!dirty || update.isPending}
              >
                <Check className="h-3.5 w-3.5" />
                {update.isPending ? "Guardando…" : "Guardar"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}