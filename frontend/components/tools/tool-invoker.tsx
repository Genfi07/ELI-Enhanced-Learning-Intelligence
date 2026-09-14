"use client";

import { useState } from "react";
import { Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useInvokeTool } from "@/lib/hooks/use-tools";
import type { Tool, ToolInvokeResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface ToolInvokerProps {
  tool: Tool;
}

/** Formulario simple por tool. En Fase 9 se genera desde JSON Schema. */
function fieldsFor(tool: Tool): { key: string; placeholder: string }[] {
  switch (tool.name) {
    case "calculator":
      return [{ key: "expression", placeholder: "2 + 3 * 4" }];
    case "datetime":
      return [
        { key: "mode", placeholder: "now | diff | add" },
        { key: "timezone", placeholder: "Europe/Madrid (opcional)" },
        { key: "base", placeholder: "2026-01-01T00:00:00Z (opcional)" },
        { key: "days", placeholder: "días a sumar (opcional)" },
      ];
    case "web_search":
      return [{ key: "query", placeholder: "qué buscar en internet" }];
    case "web_fetch":
      return [{ key: "url", placeholder: "https://…" }];
    default:
      return [];
  }
}

export function ToolInvoker({ tool }: ToolInvokerProps) {
  const fields = fieldsFor(tool);
  const [values, setValues] = useState<Record<string, string>>({});
  const [lastResult, setLastResult] = useState<ToolInvokeResult | null>(null);
  const invoke = useInvokeTool();

  function run() {
    // Limpiar valores vacíos
    const args: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      const trimmed = v.trim();
      if (!trimmed) continue;
      if (k === "days") {
        const n = Number(trimmed);
        if (!Number.isNaN(n)) args[k] = n;
      } else {
        args[k] = trimmed;
      }
    }

    invoke.mutate(
      { name: tool.name, arguments: args },
      {
        onSuccess: (res) => setLastResult(res),
      },
    );
  }

  return (
    <div>
      <div className="space-y-2">
        {fields.map((f) => (
          <Input
            key={f.key}
            placeholder={f.placeholder}
            value={values[f.key] ?? ""}
            onChange={(e) =>
              setValues((v) => ({ ...v, [f.key]: e.target.value }))
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") run();
            }}
          />
        ))}
      </div>

      <div className="mt-3 flex justify-end">
        <Button
          size="sm"
          onClick={run}
          disabled={invoke.isPending}
        >
          {invoke.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          Ejecutar
        </Button>
      </div>

      {lastResult && (
        <div
          className={cn(
            "mt-4 rounded-md border p-3 text-xs",
            lastResult.status === "OK"
              ? "border-[var(--color-success)]/30 bg-[var(--color-success)]/5"
              : lastResult.status === "PENDING_CONFIRMATION"
                ? "border-amber-400/30 bg-amber-400/5"
                : "border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5",
          )}
        >
          <div className="flex items-center justify-between">
            <span className="font-medium uppercase tracking-wider">
              {lastResult.status}
            </span>
            <span className="text-[var(--color-subtle)]">
              {lastResult.latency_ms} ms
            </span>
          </div>
          {lastResult.error && (
            <p className="mt-2 text-[var(--color-danger)]">
              {lastResult.error}
            </p>
          )}
          {lastResult.result !== null &&
            lastResult.result !== undefined && (
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[var(--color-muted)]">
                {JSON.stringify(lastResult.result, null, 2)}
              </pre>
            )}
          {lastResult.pending_action_id && (
            <p className="mt-2 text-amber-400">
              Pendiente de confirmación: {lastResult.pending_action_id}
            </p>
          )}
        </div>
      )}
    </div>
  );
}