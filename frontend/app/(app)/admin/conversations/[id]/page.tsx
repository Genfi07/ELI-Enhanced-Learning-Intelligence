"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, User, Bot, Wrench } from "lucide-react";
import { Header } from "@/components/layout/header";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useConversationMessages } from "@/lib/hooks/use-admin";
import { cn, formatRelativeDate } from "@/lib/utils";

const ROLE_ICON: Record<string, React.ElementType> = {
  user: User,
  assistant: Bot,
  tool: Wrench,
};

const ROLE_LABEL: Record<string, string> = {
  user: "Usuario",
  assistant: "ELI",
  tool: "Herramienta",
  system: "Sistema",
};

export default function AdminConversationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: user } = useCurrentUser();
  const { data: messages, isLoading } = useConversationMessages(id);

  if (!user) return null;

  const totalIn = messages?.reduce((n, m) => n + m.tokens_in, 0) ?? 0;
  const totalOut = messages?.reduce((n, m) => n + m.tokens_out, 0) ?? 0;

  return (
    <>
      <Header title="Admin · Conversación" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-8">
          <Link
            href="/admin/conversations"
            className="inline-flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Volver a conversaciones
          </Link>

          <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                Conversación
              </h1>
              <p className="mt-1 font-mono text-xs text-[var(--color-muted)]">
                {id}
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[var(--color-muted)]">
                {messages?.length ?? 0} mensajes
              </span>
              <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[var(--color-muted)]">
                {totalIn + totalOut} tokens
              </span>
            </div>
          </div>

          {isLoading && (
            <p className="mt-6 text-sm text-[var(--color-muted)]">Cargando…</p>
          )}

          <div className="mt-6 space-y-3">
            {messages?.map((m) => {
              const Icon = ROLE_ICON[m.role] ?? Wrench;
              const label = ROLE_LABEL[m.role] ?? m.role;
              const isUser = m.role === "user";
              return (
                <article
                  key={m.id}
                  className={cn(
                    "rounded-lg border p-3",
                    isUser
                      ? "border-[var(--color-border)] bg-[var(--color-surface)]"
                      : "border-[var(--color-primary)]/20 bg-[var(--color-primary-soft)]",
                  )}
                >
                  <header className="flex items-center justify-between text-[11px] text-[var(--color-subtle)]">
                    <span className="flex items-center gap-1.5 font-medium uppercase tracking-wider">
                      <Icon className="h-3 w-3" />
                      {label}
                      {m.model && (
                        <span className="font-mono text-[10px] opacity-70">
                          {m.model}
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-2">
                      {(m.tokens_in > 0 || m.tokens_out > 0) && (
                        <span className="font-mono">
                          {m.tokens_in}↑ {m.tokens_out}↓
                        </span>
                      )}
                      {formatRelativeDate(m.created_at)}
                    </span>
                  </header>
                  <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-[var(--color-foreground)]">
                    {m.content}
                  </pre>
                </article>
              );
            })}
          </div>
        </div>
      </main>
    </>
  );
}