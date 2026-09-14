"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel?: () => void;
  streaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

const MAX_ROWS = 8;
const LINE_HEIGHT = 22;

export function ChatInput({
  onSend,
  onCancel,
  streaming,
  disabled,
  placeholder = "Escribe un mensaje…",
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-resize
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const max = MAX_ROWS * LINE_HEIGHT + 24;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled || streaming) return;
    onSend(trimmed);
    setValue("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="border-t border-[var(--color-border)] bg-[var(--color-background)] p-4">
      <div
        className={cn(
          "mx-auto flex max-w-3xl items-end gap-2 rounded-xl",
          "border border-[var(--color-border-strong)] bg-[var(--color-surface)]",
          "px-3 py-2 transition-colors focus-within:border-[var(--color-primary)]",
        )}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className={cn(
            "flex-1 resize-none border-0 bg-transparent py-1.5",
            "text-sm leading-[22px] text-[var(--color-foreground)]",
            "placeholder:text-[var(--color-subtle)] focus:outline-none",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        />
        {streaming ? (
          <button
            type="button"
            onClick={onCancel}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--color-surface-hover)] text-[var(--color-muted)] transition-colors hover:text-[var(--color-foreground)]"
            aria-label="Cancelar"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || disabled}
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
              "transition-colors",
              value.trim() && !disabled
                ? "bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)]"
                : "bg-[var(--color-surface-hover)] text-[var(--color-subtle)] cursor-not-allowed",
            )}
            aria-label="Enviar"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-[var(--color-subtle)]">
        Enter para enviar · Shift + Enter para nueva línea
      </p>
    </div>
  );
}