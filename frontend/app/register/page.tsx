"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost, HttpError } from "@/lib/api/client";
import type { RegisterPayload, User } from "@/lib/api/types";

export default function RegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      toast.error("La contraseña debe tener al menos 8 caracteres");
      return;
    }
    setLoading(true);
    try {
      const user = await apiPost<User>("/auth/register", {
        name,
        email,
        password,
      } satisfies RegisterPayload);

      queryClient.setQueryData(["currentUser"], user);
      toast.success(`Cuenta creada. Bienvenido, ${user.name}`);
      window.location.href = "/chat";
      router.refresh();
    } catch (err) {
      if (err instanceof HttpError) {
        if (err.status === 409) toast.error("Ese email ya está registrado");
        else if (err.status === 429) toast.error("Demasiados intentos. Espera un minuto.");
        else if (err.status === 400) toast.error(err.message);
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
          <h1 className="text-xl font-semibold">Crear cuenta</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Empieza a usar ELI en un minuto
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="name" className="mb-1.5 block text-sm text-[var(--color-muted)]">
                Nombre
              </label>
              <Input
                id="name"
                autoComplete="name"
                required
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Tu nombre"
              />
            </div>

            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm text-[var(--color-muted)]">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
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
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
              />
            </div>

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Creando…" : "Crear cuenta"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-[var(--color-muted)]">
            ¿Ya tienes cuenta?{" "}
            <Link href="/login" className="text-[var(--color-primary)] hover:underline">
              Inicia sesión
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}