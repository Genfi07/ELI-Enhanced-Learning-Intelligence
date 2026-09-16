"use client";

import { useEffect, useState } from "react";
import { Save, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePreferences, useUpdatePreferences } from "@/lib/hooks/use-settings";
import { cn } from "@/lib/utils";

const AUTONOMY_LEVELS = [
  { level: 0, title: "Solo conversación", desc: "No ejecuta herramientas." },
  { level: 1, title: "Lectura", desc: "Consulta sin modificar nada." },
  { level: 2, title: "Herramientas internas", desc: "Calc, fecha, ops seguras." },
  { level: 3, title: "Acciones reversibles", desc: "Web, fetch de URLs." },
  { level: 4, title: "Acciones sensibles", desc: "Requieren confirmación." },
];

const RESPONSE_STYLES = [
  { value: "concise", label: "Conciso", desc: "Respuestas cortas y directas." },
  { value: "balanced", label: "Equilibrado", desc: "Ni muy corto ni muy largo." },
  { value: "detailed", label: "Detallado", desc: "Explicaciones profundas." },
] as const;

const LANGUAGES = [
  { value: "es", label: "Español" },
  { value: "en", label: "English" },
  { value: "pt", label: "Português" },
  { value: "fr", label: "Français" },
];

const THEMES = [
  { value: "dark", label: "Oscuro" },
  { value: "light", label: "Claro" },
  { value: "system", label: "Sistema" },
] as const;

export function PreferencesTab() {
  const { data: prefs, isLoading } = usePreferences();
  const update = useUpdatePreferences();

  const [autonomy, setAutonomy] = useState<number>(2);
  const [style, setStyle] = useState<string>("balanced");
  const [language, setLanguage] = useState<string>("es");
  const [theme, setTheme] = useState<string>("dark");

  useEffect(() => {
    if (!prefs) return;
    setAutonomy(prefs.autonomy_level);
    setStyle(prefs.response_style);
    setLanguage(prefs.language);
    setTheme(prefs.theme);
  }, [prefs]);

  if (isLoading || !prefs) {
    return <p className="text-sm text-[var(--color-muted)]">Cargando…</p>;
  }

  const initial = prefs;
  const maxLevel = initial.max_autonomy_level ?? 4;

  const dirty =
    autonomy !== initial.autonomy_level ||
    style !== initial.response_style ||
    language !== initial.language ||
    theme !== initial.theme;

  function save() {
    update.mutate({
      autonomy_level: autonomy,
      response_style: style as typeof initial.response_style,
      language,
      theme: theme as typeof initial.theme,
    });
  }

  return (
    <div className="space-y-6">
      {/* Autonomía */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-sm font-semibold">Nivel de autonomía de ELI</h2>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Define qué acciones puede ejecutar ELI sin pedirte permiso.
          {maxLevel < 4 && (
            <span className="ml-1 text-[var(--color-subtle)]">
              (Tu rol limita el máximo al nivel {maxLevel}.)
            </span>
          )}
        </p>
        <div className="mt-4 space-y-1.5">
          {AUTONOMY_LEVELS.map((l) => {
            const active = autonomy === l.level;
            const locked = l.level > maxLevel;
            return (
              <button
                key={l.level}
                type="button"
                onClick={() => !locked && setAutonomy(l.level)}
                disabled={locked}
                title={locked ? "Requiere un rol superior" : undefined}
                className={cn(
                  "flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors",
                  locked
                    ? "cursor-not-allowed border-[var(--color-border)] opacity-40"
                    : active
                      ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                      : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium",
                    active && !locked
                      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                      : "border-[var(--color-border-strong)] text-[var(--color-muted)]",
                  )}
                >
                  {locked ? <Lock className="h-3 w-3" /> : l.level}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{l.title}</p>
                  <p className="text-[11px] text-[var(--color-muted)]">{l.desc}</p>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Estilo de respuesta */}
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-sm font-semibold">Estilo de respuesta</h2>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Cómo prefieres que ELI te conteste por defecto.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {RESPONSE_STYLES.map((s) => {
            const active = style === s.value;
            return (
              <button
                key={s.value}
                type="button"
                onClick={() => setStyle(s.value)}
                className={cn(
                  "rounded-md border p-3 text-left transition-colors",
                  active
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                    : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]",
                )}
              >
                <p className="text-sm font-medium">{s.label}</p>
                <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
                  {s.desc}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {/* Idioma + tema */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-sm font-semibold">Idioma</h2>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="mt-3 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-primary)] focus:outline-none"
          >
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-sm font-semibold">Tema</h2>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            className="mt-3 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-primary)] focus:outline-none"
          >
            {THEMES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {/* Guardar */}
      <div className="flex justify-end">
        <Button onClick={save} disabled={!dirty || update.isPending}>
          <Save className="h-3.5 w-3.5" />
          {update.isPending ? "Guardando…" : "Guardar preferencias"}
        </Button>
      </div>
    </div>
  );
}