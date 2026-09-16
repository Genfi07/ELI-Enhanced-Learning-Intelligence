"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Settings,
} from "lucide-react";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { cn } from "@/lib/utils";

interface AdminTab {
  href: string;
  label: string;
  icon: React.ElementType;
  exact?: boolean;
}

const ADMIN_TABS: AdminTab[] = [
  {
    href: "/admin",
    label: "Dashboard",
    icon: LayoutDashboard,
    exact: true,
  },
  { href: "/admin/users", label: "Usuarios", icon: Users },
  { href: "/admin/config", label: "Configuración", icon: Settings },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: user, isLoading } = useCurrentUser();

  useEffect(() => {
    if (
      !isLoading &&
      user &&
      user.role !== "ADMIN" &&
      user.role !== "SUPER_ADMIN"
    ) {
      router.replace("/chat");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--color-muted)]">
        Cargando…
      </div>
    );
  }

  if (user.role !== "ADMIN" && user.role !== "SUPER_ADMIN") {
    return null;
  }

  function isActive(tab: AdminTab) {
    if (tab.exact) {
      return pathname === tab.href;
    }
    return pathname === tab.href || pathname.startsWith(tab.href + "/");
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-[var(--color-border)] bg-[var(--color-background)] px-6">
        <nav className="mx-auto flex max-w-5xl items-center gap-1">
          {ADMIN_TABS.map((tab) => {
            const Icon = tab.icon;
            const active = isActive(tab);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "relative flex items-center gap-2 px-3 py-3 text-sm transition-colors",
                  active
                    ? "text-[var(--color-foreground)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {tab.label}
                {active && (
                  <span className="absolute inset-x-0 -bottom-px h-0.5 bg-[var(--color-primary)]" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {children}
    </div>
  );
}