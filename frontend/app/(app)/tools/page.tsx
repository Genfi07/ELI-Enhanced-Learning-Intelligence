"use client";

import { useState } from "react";
import {
  Wrench,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Ban,
  Sparkles,
  ChevronDown,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { FlowsGrid } from "@/components/tools/flows-grid";
import { ToolCard } from "@/components/tools/tool-card";
import { ToolInvoker } from "@/components/tools/tool-invoker";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useTools, useToolCalls } from "@/lib/hooks/use-tools";
import { cn, formatRelativeDate } from "@/lib/utils";

function effectiveAutonomy(role: string): number {
  return role === "ADMIN" || role === "SUPER_ADMIN" ? 4 : 2;
}

function statusIcon(status: string) {
  switch (status) {
    case "OK":
      return { Icon: CheckCircle2, className: "text-[var(--color-success)]" };
    case "DENIED":
      return { Icon: Ban, className: "text-[var(--color-warning)]" };
    case "PENDING_CONFIRMATION":
      return { Icon: Clock, className: "text-amber-400" };
    case "TIMEOUT":
    case "ERROR":
      return { Icon: XCircle, className: "text-[var(--color-danger)]" };
    default:
      return { Icon: Clock, className: "text-[var(--color-muted)]" };
  }
}

export default function ToolsPage() {
  const { data: user } = useCurrentUser();
  const { data: tools, isLoading } = useTools();
  const { data: calls } = useToolCalls(15);
  const [selected, setSelected] = useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);

  if (!user) return null;

  const autonomy = effectiveAutonomy(user.role);
  const selectedTool = tools?.find((t) => t.name === selected);

  return (
    <>
      <Header title="Herramientas" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-8">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Herramientas y flujos
            </h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Empieza por un flujo para tareas comunes, o prueba herramientas
              individuales. Tu nivel de autonomía actual es{" "}
              <strong>{autonomy}</strong>.
            </p>
          </div>

          {/* Flujos */}
          <section className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
              <Sparkles className="h-3 w-3" />
              Flujos rápidos
            </h2>
            <FlowsGrid />
          </section>

          {/* Herramientas individuales (colapsable) */}
          <section className="mt-10">
            <button
              type="button"
              onClick={() => setToolsOpen((v) => !v)}
              className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-subtle)]">
                <Wrench className="h-3 w-3" />
                Herramientas individuales ({tools?.length ?? 0})
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-[var(--color-subtle)] transition-transform",
                  toolsOpen && "rotate-180",
                )}
              />
            </button>

            {toolsOpen && (
              <div className="mt-3 grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div>
                  <div className="space-y-2">
                    {isLoading && (
                      <p className="text-sm text-[var(--color-muted)]">
                        Cargando…
                      </p>
                    )}
                    {tools?.map((t) => (
                      <ToolCard
                        key={t.name}
                        tool={t}
                        userAutonomyLevel={autonomy}
                        selected={selected === t.name}
                        onSelect={() => setSelected(t.name)}
                      />
                    ))}
                  </div>
                </div>

                <div>
                  {selectedTool ? (
                    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                      <div className="flex items-center gap-2">
                        <Wrench className="h-4 w-4 text-[var(--color-primary)]" />
                        <p className="text-sm font-medium">
                          {selectedTool.name}
                        </p>
                      </div>
                      <p className="mt-1 text-xs text-[var(--color-muted)]">
                        {selectedTool.description}
                      </p>
                      <div className="mt-4">
                        <ToolInvoker tool={selectedTool} />
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-full min-h-64 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center">
                      <p className="text-sm text-[var(--color-muted)]">
                        Selecciona una herramienta de la izquierda para
                        probarla.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Historial */}
          <section className="mt-10">
            <h2 className="text-sm font-medium text-[var(--color-muted)]">
              Historial reciente
            </h2>
            <div className="mt-3 space-y-1.5">
              {!calls || calls.length === 0 ? (
                <p className="text-xs text-[var(--color-subtle)]">
                  Sin llamadas registradas todavía.
                </p>
              ) : (
                calls.map((c) => {
                  const { Icon, className } = statusIcon(c.status);
                  return (
                    <div
                      key={c.id}
                      className="flex items-center gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs"
                    >
                      <Icon className={cn("h-3.5 w-3.5 shrink-0", className)} />
                      <span className="font-mono text-[var(--color-foreground)]">
                        {c.tool_name}
                      </span>
                      <span className="text-[var(--color-subtle)]">
                        {c.status}
                      </span>
                      <span className="ml-auto text-[var(--color-subtle)]">
                        {c.latency_ms} ms
                      </span>
                      <span className="text-[var(--color-subtle)]">
                        {formatRelativeDate(c.created_at)}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </main>
    </>
  );
}