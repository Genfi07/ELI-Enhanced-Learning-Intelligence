"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Search,
  UserX,
  UserCheck,
  Trash2,
  UserPlus,
  ShieldCheck,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { UserCreateDialog } from "@/components/admin/user-create-dialog";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import {
  useAdminUsers,
  useBlockUser,
  useChangeUserRole,
  useDeleteUser,
  usePromoteToSuper,
  useUnblockUser,
} from "@/lib/hooks/use-admin";
import { cn, formatRelativeDate } from "@/lib/utils";
import { useConfirm } from "@/lib/stores/confirm-store";

const ROLE_OPTIONS = ["USER", "MODERATOR", "ADMIN", "SUPER_ADMIN"];

const ROLE_COLOR: Record<string, string> = {
  USER: "bg-[var(--color-surface-hover)] text-[var(--color-muted)]",
  MODERATOR: "bg-blue-500/10 text-blue-400",
  ADMIN: "bg-purple-500/10 text-purple-400",
  SUPER_ADMIN: "bg-amber-500/10 text-amber-400",
};

export default function AdminUsersPage() {
  const { data: current } = useCurrentUser();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const { data: users, isLoading } = useAdminUsers(search || undefined);
  const blockMutation = useBlockUser();
  const unblockMutation = useUnblockUser();
  const roleMutation = useChangeUserRole();
  const deleteMutation = useDeleteUser();
  const promoteMutation = usePromoteToSuper();
  const confirm = useConfirm();

  if (!current) return null;
  const isSuperAdmin = current.role === "SUPER_ADMIN";

  async function handleDelete(email: string, id: string) {
    const ok = await confirm({
      title: "Eliminar usuario",
      message: `¿Seguro que quieres eliminar a ${email}? Se borrarán sus conversaciones, memorias y archivos. Esta acción no se puede deshacer.`,
      confirmText: "Eliminar usuario",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    deleteMutation.mutate(id);
  }

  async function handlePromote(name: string, id: string) {
    const ok = await confirm({
      title: "Promover a SUPER_ADMIN",
      message: `${name} tendrá acceso total al sistema, incluida la creación de otros SUPER_ADMINs y la modificación de la configuración. ¿Confirmas?`,
      confirmText: "Promover",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    promoteMutation.mutate(id);
  }

  return (
    <>
      <Header title="Admin · Usuarios" user={current} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-6 py-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                Usuarios
              </h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Gestiona cuentas, roles y bloqueos.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative w-56">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-subtle)]" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar…"
                  className="pl-8"
                />
              </div>
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <UserPlus className="h-3.5 w-3.5" />
                Nuevo
              </Button>
            </div>
          </div>

          <div className="mt-6 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] text-[11px] uppercase tracking-wider text-[var(--color-subtle)]">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">Usuario</th>
                  <th className="px-4 py-2.5 text-left font-medium">Rol</th>
                  <th className="px-4 py-2.5 text-left font-medium">Estado</th>
                  <th className="px-4 py-2.5 text-left font-medium">
                    Último login
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-6 text-center text-xs text-[var(--color-muted)]"
                    >
                      Cargando…
                    </td>
                  </tr>
                )}
                {users?.map((u) => {
                  const isSelf = u.id === current.id;
                  const canPromote =
                    isSuperAdmin && u.role !== "SUPER_ADMIN" && !isSelf;
                  return (
                    <tr
                      key={u.id}
                      className="border-b border-[var(--color-border)] last:border-0"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/admin/users/${u.id}`}
                          className="font-medium hover:text-[var(--color-primary)] hover:underline"
                        >
                          {u.name}
                        </Link>
                        <p className="text-xs text-[var(--color-muted)]">
                          {u.email}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={u.role}
                          disabled={isSelf || roleMutation.isPending}
                          onChange={(e) =>
                            roleMutation.mutate({
                              id: u.id,
                              role: e.target.value,
                            })
                          }
                          className={cn(
                            "cursor-pointer rounded border-0 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]",
                            ROLE_COLOR[u.role] ??
                              "bg-[var(--color-surface-hover)]",
                            isSelf && "cursor-not-allowed opacity-60",
                          )}
                        >
                          {ROLE_OPTIONS.map((r) => (
                            <option
                              key={r}
                              value={r}
                              className="bg-[var(--color-surface)]"
                            >
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 text-[11px] font-medium uppercase",
                            u.status === "ACTIVE"
                              ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                              : u.status === "BLOCKED"
                                ? "bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
                                : "bg-[var(--color-surface-hover)] text-[var(--color-muted)]",
                          )}
                        >
                          {u.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-[var(--color-muted)]">
                        {u.last_login_at
                          ? formatRelativeDate(u.last_login_at)
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          {canPromote && (
                            <button
                              type="button"
                              onClick={() => handlePromote(u.name, u.id)}
                              disabled={promoteMutation.isPending}
                              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-amber-400 disabled:opacity-30"
                              title="Promover a SUPER_ADMIN"
                            >
                              <ShieldCheck className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {u.status === "ACTIVE" ? (
                            <button
                              type="button"
                              disabled={isSelf}
                              onClick={() => blockMutation.mutate({ id: u.id })}
                              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)] disabled:cursor-not-allowed disabled:opacity-30"
                              title="Bloquear"
                            >
                              <UserX className="h-3.5 w-3.5" />
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={isSelf}
                              onClick={() => unblockMutation.mutate(u.id)}
                              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-success)] disabled:cursor-not-allowed disabled:opacity-30"
                              title="Desbloquear"
                            >
                              <UserCheck className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {isSuperAdmin && (
                            <button
                              type="button"
                              disabled={isSelf}
                              onClick={() => handleDelete(u.email, u.id)}
                              className="rounded p-1.5 text-[var(--color-subtle)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-danger)] disabled:cursor-not-allowed disabled:opacity-30"
                              title="Eliminar"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <UserCreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        isSuperAdmin={isSuperAdmin}
      />
    </>
  );
}