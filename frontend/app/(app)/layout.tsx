"use client";

import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { Sidebar } from "@/components/layout/sidebar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-[var(--color-muted)]">
        Cargando…
      </div>
    );
  }

  if (isError || !user) {
    if (typeof window !== "undefined") window.location.href = "/login";
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar user={user} />
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
      <ConfirmDialog />
    </div>
  );
}