"use client";

import Link from "next/link";
import {
  Users,
  UserCheck,
  UserX,
  MessageSquare,
  Brain,
  FileText,
  Wrench,
  Hash,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import {
  useAnalyticsOverview,
  useAuditLogs,
  useSystemHealth,
  useTimeseries,
} from "@/lib/hooks/use-admin";
import { cn, formatRelativeDate } from "@/lib/utils";

interface DashboardCard {
  label: string;
  value: number | string | undefined;
  icon: LucideIcon;
  href?: string;
}

export default function AdminDashboard() {
  const { data: user } = useCurrentUser();
  const { data: overview } = useAnalyticsOverview();
  const { data: timeseries } = useTimeseries(7);
  const { data: health } = useSystemHealth();
  const { data: audit } = useAuditLogs(10);

  if (!user) return null;

  const cards: DashboardCard[] = [
    { label: "Usuarios", value: overview?.users_total, icon: Users },
    { label: "Activos", value: overview?.users_active, icon: UserCheck },
    { label: "Bloqueados", value: overview?.users_blocked, icon: UserX },
    {
      label: "Conversaciones",
      value: overview?.conversations_total,
      icon: MessageSquare,
      href: "/admin/conversations",
    },
    { label: "Mensajes", value: overview?.messages_total, icon: Hash },
    { label: "Memorias", value: overview?.memories_total, icon: Brain },
    { label: "Documentos", value: overview?.documents_total, icon: FileText },
    { label: "Tool calls", value: overview?.tool_calls_total, icon: Wrench },
    { label: "Tokens", value: overview?.tokens_total, icon: Hash },
    {
      label: "Coste estimado",
      value:
        overview !== undefined
          ? `$${overview.cost_estimate_usd.toFixed(4)}`
          : undefined,
      icon: DollarSign,
    },
    { label: "Errores", value: overview?.errors_total, icon: AlertTriangle },
  ];

  return (
    <>
      <Header title="Admin" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">Panel admin</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Estado del sistema, uso, configuración y auditoría.
          </p>

          {/* Resumen */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {cards.map((c) => {
              const Icon = c.icon;
              const baseClass =
                "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-colors";
              const content = (
                <>
                  <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-[var(--color-subtle)]">
                    <Icon className="h-3 w-3" />
                    {c.label}
                  </div>
                  <div className="mt-2 text-xl font-semibold">
                    {c.value ?? "—"}
                  </div>
                </>
              );
              if (c.href) {
                return (
                  <Link
                    key={c.label}
                    href={c.href}
                    className={cn(
                      baseClass,
                      "hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]",
                    )}
                  >
                    {content}
                  </Link>
                );
              }
              return (
                <div key={c.label} className={baseClass}>
                  {content}
                </div>
              );
            })}
          </div>

          {/* Health */}
          {health && (
            <div className="mt-8">
              <h2 className="mb-3 text-sm font-medium text-[var(--color-muted)]">
                Estado del sistema
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                <HealthCard
                  label="Estado"
                  value={health.status}
                  ok={health.status === "ok"}
                />
                <HealthCard
                  label="Base de datos"
                  value={health.database}
                  ok={health.database === "ok"}
                />
                <HealthCard label="Entorno" value={health.env} />
                <HealthCard label="Versión" value={health.version} />
                <HealthCard label="LLM" value={health.llm_provider} />
                <HealthCard
                  label="Embeddings"
                  value={health.embeddings_provider}
                />
                <HealthCard
                  label="Tools registradas"
                  value={String(health.tools_count)}
                />
              </div>
            </div>
          )}

          {/* Serie */}
          {timeseries && (
            <div className="mt-8">
              <h2 className="mb-3 text-sm font-medium text-[var(--color-muted)]">
                Últimos {timeseries.days} días
              </h2>
              <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--color-border)] text-[11px] uppercase tracking-wider text-[var(--color-subtle)]">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Fecha</th>
                      <th className="px-4 py-2 text-right font-medium">
                        Mensajes
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        Tokens
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        Errores
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeseries.points.map((p) => (
                      <tr
                        key={p.date}
                        className="border-b border-[var(--color-border)] last:border-0"
                      >
                        <td className="px-4 py-2">{p.date}</td>
                        <td className="px-4 py-2 text-right">{p.messages}</td>
                        <td className="px-4 py-2 text-right">{p.tokens}</td>
                        <td className="px-4 py-2 text-right">{p.errors}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Audit */}
          <div className="mt-8">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-muted)]">
              Últimas acciones administrativas
            </h2>
            {!audit || audit.length === 0 ? (
              <p className="text-xs text-[var(--color-subtle)]">
                Sin acciones registradas.
              </p>
            ) : (
              <div className="space-y-1.5">
                {audit.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs"
                  >
                    <code className="rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 text-[11px] text-[var(--color-primary)]">
                      {a.action}
                    </code>
                    <span className="text-[var(--color-muted)]">
                      {a.entity_type ?? "—"}
                      {a.entity_id ? `:${a.entity_id.slice(0, 12)}` : ""}
                    </span>
                    <span className="ml-auto text-[var(--color-subtle)]">
                      {a.actor_user_id
                        ? a.actor_user_id.slice(0, 8) + "…"
                        : "sistema"}
                    </span>
                    <span className="text-[var(--color-subtle)]">
                      {formatRelativeDate(a.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
}

function HealthCard({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-subtle)]">
        {label}
      </p>
      <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium">
        {ok !== undefined &&
          (ok ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-success)]" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-[var(--color-danger)]" />
          ))}
        <span className={cn(ok === false && "text-[var(--color-danger)]")}>
          {value}
        </span>
      </p>
    </div>
  );
}