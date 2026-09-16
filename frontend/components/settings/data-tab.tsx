"use client";

import { useState } from "react";
import { Download, Trash2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  exportMyData,
  useDeleteMyAccount,
} from "@/lib/hooks/use-settings";
import { useConfirm } from "@/lib/stores/confirm-store";
import { toast } from "sonner";
import type { User } from "@/lib/api/types";

export function DataTab({ user }: { user: User }) {
  const [exporting, setExporting] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState("");
  const deleteAccount = useDeleteMyAccount();
  const confirmModal = useConfirm();

  async function handleExport() {
    setExporting(true);
    try {
      await exportMyData();
      toast.success("Datos exportados");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    if (confirmEmail.trim().toLowerCase() !== user.email.toLowerCase()) {
      toast.error("El email no coincide");
      return;
    }
    const ok = await confirmModal({
      title: "Eliminar tu cuenta",
      message:
        "Se borrarán TODAS tus conversaciones, memorias y archivos. Tu cuenta quedará anonimizada. Esta acción NO se puede deshacer.",
      confirmText: "Eliminar mi cuenta",
      cancelText: "Cancelar",
      variant: "danger",
    });
    if (!ok) return;
    deleteAccount.mutate(confirmEmail.trim().toLowerCase());
  }

  const canDelete =
    confirmEmail.trim().toLowerCase() === user.email.toLowerCase() &&
    !deleteAccount.isPending;

  return (
    <div className="space-y-6">
      {/* Exportar */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <header className="flex items-center gap-2">
          <Download className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="text-sm font-semibold">Exportar mis datos</h2>
        </header>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Descarga un archivo JSON con tu perfil, conversaciones, mensajes,
          memorias y documentos.
        </p>
        <div className="mt-4 flex justify-end">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExport}
            disabled={exporting}
          >
            <Download className="h-3.5 w-3.5" />
            {exporting ? "Preparando…" : "Descargar mis datos"}
          </Button>
        </div>
      </section>

      {/* Zona peligrosa */}
      <section className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 p-5">
        <header className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-[var(--color-danger)]" />
          <h2 className="text-sm font-semibold text-[var(--color-danger)]">
            Zona peligrosa
          </h2>
        </header>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Eliminar tu cuenta borra permanentemente todas tus conversaciones,
          memorias y archivos. La acción no se puede deshacer.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-[var(--color-subtle)]">
              Escribe <span className="font-mono">{user.email}</span> para
              confirmar
            </label>
            <Input
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              placeholder={user.email}
              className="mt-1"
            />
          </div>
          <div className="flex justify-end">
            <Button
              variant="danger"
              size="sm"
              onClick={handleDelete}
              disabled={!canDelete}
            >
              <Trash2 className="h-3.5 w-3.5" />
              {deleteAccount.isPending ? "Eliminando…" : "Eliminar mi cuenta"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}