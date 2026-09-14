"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost, HttpError } from "@/lib/api/client";
import type { LoginPayload, User } from "@/lib/api/types";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const from = params.get("from") ?? "/chat";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const user = await apiPost<User>("/auth/login", {
        email,
        password,
      } satisfies LoginPayload);

      // Sembramos el user en la caché de TanStack Query para que el shell
      // lo encuentre sin esperar al GET /auth/me.
      queryClient.setQueryData(["currentUser"], user);

          toast.success(`Bienvenido, ${user.name}`);
      // Full reload para asegurar que el navegador envía la cookie ya
      // persistida al pedir /chat. Con router.replace a veces la middleware
      // no ve la cookie y redirige de vuelta a /login.
      window.location.href = from;
    } catch (err) {
      if (err instanceof HttpError) {
        if (err.status === 401) toast.error("Email o contraseña incorrectos");
        else if (err.status === 429) toast.error("Demasiados intentos. Espera un minuto.");
        else toast.error(err.message);
      } else {
        toast.error("Error de red");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          className="mb-8 block text-center text-2xl font-semibold tracking-tight"
        >
          ELI
        </Link>

        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8">
          <h1 className="text-xl font-semibold">Iniciar sesión</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Accede con tu cuenta
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm text-[var(--color-muted)]">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@email.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm text-[var(--color-muted)]">
                Contraseña
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Entrando…" : "Entrar"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-[var(--color-muted)]">
            ¿No tienes cuenta?{" "}
            <Link href="/register" className="text-[var(--color-primary)] hover:underline">
              Crear una
            </Link>
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-[var(--color-subtle)]">
          Sesión con cookie segura · caduca en 30 días
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}