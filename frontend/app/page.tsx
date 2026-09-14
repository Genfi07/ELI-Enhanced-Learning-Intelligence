import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h1 className="text-4xl font-semibold tracking-tight">
          ELI
          <span className="ml-2 text-lg font-normal text-[var(--color-muted)]">
            · Enhanced Learning Intelligence
          </span>
        </h1>
        <p className="mt-4 text-[var(--color-muted)]">
          Sistema de IA con memoria persistente, RAG, planificación y
          herramientas.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link
            href="/login"
            className="rounded-md bg-[var(--color-primary)] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-primary-hover)]"
          >
            Entrar
          </Link>
          <Link
            href="/register"
            className="rounded-md border border-[var(--color-border-strong)] px-5 py-2.5 text-sm font-medium transition hover:bg-[var(--color-surface-hover)]"
          >
            Crear cuenta
          </Link>
        </div>
        <p className="mt-6 text-xs text-[var(--color-subtle)]">
          Interfaz moderna · Fase 8 en construcción
        </p>
      </div>
    </main>
  );
}