"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  MessageSquare,
  Brain,
  FileText,
  Wrench,
  Settings,
  ShieldCheck,
  Plus,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/api/types";
import { ConversationList } from "@/components/chat/conversation-list";
import { useNewChatStore } from "@/lib/stores/new-chat-store";

interface SidebarProps {
  user: User;
  onNavigate?: () => void;
}

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/memory", label: "Memoria", icon: Brain },
  { href: "/goals", label: "Metas", icon: Target },
  { href: "/files", label: "Archivos", icon: FileText },
  { href: "/tools", label: "Herramientas", icon: Wrench },
  { href: "/admin", label: "Admin", icon: ShieldCheck, adminOnly: true },
  { href: "/settings", label: "Ajustes", icon: Settings },
];

export function Sidebar({ user, onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const bumpNewChat = useNewChatStore((s) => s.bump);
  const isAdmin = user.role === "ADMIN" || user.role === "SUPER_ADMIN";

  function handleNewChat() {
    bumpNewChat();
    router.push("/chat");
    onNavigate?.();
  }

  return (
    <aside
      className="flex h-full w-64 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]"
      onClick={(e) => {
        // Cierra el menú en móvil al pulsar cualquier enlace o botón dentro del sidebar
        const target = e.target as HTMLElement;
        if (target.closest("a, button")) onNavigate?.();
      }}
    >
      <div className="flex h-14 shrink-0 items-center border-b border-[var(--color-border)] px-5">
        <Link
          href="/chat"
          className="text-lg font-semibold tracking-tight"
          onClick={() => onNavigate?.()}
        >
          ELI
        </Link>
      </div>

      <div className="shrink-0 p-3">
        <button
          type="button"
          onClick={handleNewChat}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-md",
            "border border-[var(--color-border-strong)] px-3 py-2 text-sm font-medium",
            "transition-colors hover:bg-[var(--color-surface-hover)]",
          )}
        >
          <Plus className="h-4 w-4" />
          Nuevo chat
        </button>
      </div>

      <nav className="shrink-0 space-y-0.5 px-2 pb-2">
        {NAV.filter((item) => !item.adminOnly || isAdmin).map((item) => {
          const Icon = item.icon;
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => onNavigate?.()}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-1.5 text-sm transition-colors",
                active
                  ? "bg-[var(--color-surface-hover)] text-[var(--color-foreground)]"
                  : "text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/*
        ConversationList se encarga de sus propios clics.
        Le pasamos onNavigate para que cierre el menú al seleccionar una conversación.
      */}
      <ConversationList onNavigate={onNavigate} />

      <div className="shrink-0 border-t border-[var(--color-border)] p-3">
        <p className="px-2 text-xs text-[var(--color-subtle)]">
          ELI · v0.1.0
        </p>
      </div>
    </aside>
  );
}