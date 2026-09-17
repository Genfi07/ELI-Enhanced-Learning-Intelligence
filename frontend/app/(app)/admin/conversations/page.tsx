"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, MessageSquare, ExternalLink } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useAllConversations } from "@/lib/hooks/use-admin";
import { formatRelativeDate } from "@/lib/utils";

export default function AdminConversationsPage() {
  const { data: user } = useCurrentUser();
  const [search, setSearch] = useState("");
  const { data: conversations, isLoading } = useAllConversations({
    search: search || undefined,
    limit: 100,
  });

  if (!user) return null;

  return (
    <>
      <Header title="Admin · Conversaciones" user={user} />
      <main className="flex-1 overflow-y-auto min-h-0">
        <div className="mx-auto w-full max-w-5xl px-3 py-6 md:px-6 md:py-8">
          {/* Cabecera + buscador */}
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight md:text-2xl">
                Conversaciones
              </h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Todas las conversaciones de la plataforma. Filtra por usuario o
                título.
              </p>
            </div>
            <div className="relative w-full md:w-72">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-subtle)]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por usuario o título…"
                className="pl-8"
              />
            </div>
          </div>

          {/* Tabla con scroll horizontal en móvil */}
          <div className="mt-6 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="border-b border-[var(--color-border)] text-[11px] uppercase tracking-wider text-[var(--color-subtle)]">
                  <tr>
                    <th className="px-4 py-2.5 text-left font-medium">
                      Conversación
                    </th>
                    <th className="px-4 py-2.5 text-left font-medium">
                      Usuario
                    </th>
                    <th className="px-4 py-2.5 text-right font-medium">
                      Msgs
                    </th>
                    <th className="px-4 py-2.5 text-left font-medium">
                      Actualizada
                    </th>
                    <th className="px-4 py-2.5 text-right font-medium"></th>
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
                  {!isLoading && (conversations?.length ?? 0) === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-4 py-6 text-center text-xs text-[var(--color-muted)]"
                      >
                        Sin conversaciones.
                      </td>
                    </tr>
                  )}
                  {conversations?.map((c) => (
                    <tr
                      key={c.id}
                      className="border-b border-[var(--color-border)] last:border-0"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <MessageSquare className="h-3.5 w-3.5 shrink-0 text-[var(--color-subtle)]" />
                          <span className="font-medium">{c.title}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/admin/users/${c.user_id}`}
                          className="text-xs text-[var(--color-primary)] hover:underline"
                        >
                          {c.user_name ??
                            c.user_email ??
                            c.user_id.slice(0, 8)}
                        </Link>
                        {c.user_email && (
                          <p className="text-[11px] text-[var(--color-subtle)]">
                            {c.user_email}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-xs">
                        {c.messages_count}
                      </td>
                      <td className="px-4 py-3 text-xs text-[var(--color-muted)]">
                        {formatRelativeDate(c.updated_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/admin/conversations/${c.id}`}
                          className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)] hover:underline"
                        >
                          Ver
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}