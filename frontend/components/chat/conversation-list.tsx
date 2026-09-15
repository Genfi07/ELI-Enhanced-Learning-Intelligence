"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { MessageSquare, Trash2, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useConversations,
  useDeleteConversation,
} from "@/lib/hooks/use-conversations";
import { useNewChatStore } from "@/lib/stores/new-chat-store";
import { useConfirm } from "@/lib/stores/confirm-store";

export function ConversationList() {
  const pathname = usePathname();
  const router = useRouter();
  const bumpNewChat = useNewChatStore((s) => s.bump);
  const { data: conversations, isLoading } = useConversations();
  const deleteMutation = useDeleteConversation();
  const [search, setSearch] = useState("");
  const confirm = useConfirm();

  const filtered = (conversations ?? []).filter((c) =>
    search.trim()
      ? (c.title || "").toLowerCase().includes(search.toLowerCase())
      : true,
  );

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    const ok = await confirm({
      title: "Eliminar conversación",
      message: "Se borrará el historial de esta conversación. Las memorias creadas se conservan.",
      confirmText: "Eliminar",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    deleteMutation.mutate(id, {
      onSuccess: () => {
        if (pathname === `/chat/${id}`) {
          bumpNewChat();
          router.push("/chat");
        }
      },
    });
  }

  const activeId = pathname.startsWith("/chat/")
    ? pathname.slice("/chat/".length)
    : null;

  return (
    <div className="flex flex-1 flex-col overflow-hidden border-t border-[var(--color-border)]">
      <div className="px-3 pt-3">
        <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-subtle)]">
          Conversaciones
        </p>
        <div className="relative mt-2">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-subtle)]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar…"
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-background)] py-1 pl-7 pr-2 text-xs text-[var(--color-foreground)] placeholder:text-[var(--color-subtle)] focus:border-[var(--color-primary)] focus:outline-none"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && (
          <p className="px-2 py-1 text-xs text-[var(--color-subtle)]">
            Cargando…
          </p>
        )}
        {!isLoading && filtered.length === 0 && (
          <p className="px-2 py-1 text-xs text-[var(--color-subtle)]">
            {search ? "Sin resultados" : "Sin conversaciones"}
          </p>
        )}
        {filtered.map((c) => {
          const isActive = c.id === activeId;
          return (
            <Link
              key={c.id}
              href={`/chat/${c.id}`}
              className={cn(
                "group flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition-colors",
                isActive
                  ? "bg-[var(--color-surface-hover)] text-[var(--color-foreground)]"
                  : "text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
              )}
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                <span className="truncate text-xs">
                  {c.title || "Sin título"}
                </span>
              </div>
              <button
                type="button"
                onClick={(e) => handleDelete(e, c.id)}
                className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                aria-label="Eliminar conversación"
              >
                <Trash2 className="h-3.5 w-3.5 text-[var(--color-subtle)] hover:text-[var(--color-danger)]" />
              </button>
            </Link>
          );
        })}
      </div>
    </div>
  );
}