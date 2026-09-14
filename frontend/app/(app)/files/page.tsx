"use client";

import { FileText } from "lucide-react";
import { Header } from "@/components/layout/header";
import { FileUpload } from "@/components/files/file-upload";
import { FileRow } from "@/components/files/file-row";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useFiles } from "@/lib/hooks/use-files";

export default function FilesPage() {
  const { data: user } = useCurrentUser();
  const { data: files, isLoading } = useFiles();

  if (!user) return null;

  const readyCount = files?.filter((f) => f.status === "READY").length ?? 0;

  return (
    <>
      <Header title="Archivos" user={user} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Archivos</h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Sube documentos y ELI podrá responder preguntas sobre ellos.
              Todo se procesa y se guarda en tu cuenta.
            </p>
          </div>

          <div className="mt-6">
            <FileUpload />
          </div>

          <div className="mt-8">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-[var(--color-muted)]">
                Tus documentos
              </h2>
              {files && files.length > 0 && (
                <p className="text-xs text-[var(--color-subtle)]">
                  {readyCount} listos · {files.length} totales
                </p>
              )}
            </div>

            <div className="mt-3 space-y-2">
              {isLoading && (
                <p className="text-sm text-[var(--color-muted)]">Cargando…</p>
              )}
              {!isLoading && (!files || files.length === 0) && (
                <div className="rounded-lg border border-dashed border-[var(--color-border)] py-12 text-center">
                  <FileText className="mx-auto h-8 w-8 text-[var(--color-subtle)]" />
                  <p className="mt-3 text-sm text-[var(--color-muted)]">
                    Todavía no has subido ningún archivo.
                  </p>
                </div>
              )}
              {files?.map((doc) => (
                <FileRow key={doc.id} doc={doc} />
              ))}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}