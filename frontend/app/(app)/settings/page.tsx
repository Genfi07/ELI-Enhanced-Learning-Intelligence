"use client";

import { useState } from "react";
import {
  User as UserIcon,
  Shield,
  SlidersHorizontal,
  Database,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { AccountTab } from "@/components/settings/account-tab";
import { SecurityTab } from "@/components/settings/security-tab";
import { PreferencesTab } from "@/components/settings/preferences-tab";
import { DataTab } from "@/components/settings/data-tab";
import { cn } from "@/lib/utils";

type TabId = "account" | "security" | "preferences" | "data";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
}

const TABS: Tab[] = [
  { id: "account", label: "Cuenta", icon: UserIcon },
  { id: "security", label: "Seguridad", icon: Shield },
  { id: "preferences", label: "Preferencias", icon: SlidersHorizontal },
  { id: "data", label: "Datos", icon: Database },
];

export default function SettingsPage() {
  const { data: user } = useCurrentUser();
  const [tab, setTab] = useState<TabId>("account");

  if (!user) return null;

  return (
    <>
      <Header title="Ajustes" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <h1 className="text-2xl font-semibold tracking-tight">Ajustes</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Tu perfil, seguridad, preferencias y datos.
          </p>

          <nav className="mt-6 flex items-center gap-1 border-b border-[var(--color-border)]">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "relative flex items-center gap-2 px-3 py-3 text-sm transition-colors",
                    active
                      ? "text-[var(--color-foreground)]"
                      : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                  {active && (
                    <span className="absolute inset-x-0 -bottom-px h-0.5 bg-[var(--color-primary)]" />
                  )}
                </button>
              );
            })}
          </nav>

          <div className="mt-8">
            {tab === "account" && <AccountTab user={user} />}
            {tab === "security" && <SecurityTab />}
            {tab === "preferences" && <PreferencesTab />}
            {tab === "data" && <DataTab user={user} />}
          </div>
        </div>
      </main>
    </>
  );
}