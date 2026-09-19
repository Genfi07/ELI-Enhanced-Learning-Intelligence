"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square, Paperclip, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ACCEPTED_ATTR, type Attachment } from "@/lib/hooks/use-attachment";
import { ChatAttachment } from "./chat-attachment";

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel?: () => void;
  onAttach?: (file: File) => void;
  onRemoveAttachment?: () => void;
  attachment?: Attachment | null;
  streaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
  /** Texto inicial para el composer. Se aplica una sola vez al montar. */
  initialValue?: string;
}

const MAX_ROWS = 8;
const LINE_HEIGHT = 22;

export function ChatInput({
  onSend,
  onCancel,
  onAttach,
  onRemoveAttachment,
  attachment,
  streaming,
  disabled,
  placeholder = "Escribe un mensaje…",
  initialValue,
}: ChatInputProps) {
  const [value, setValue] = useState(initialValue ?? "");
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-resize
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const max = MAX_ROWS * LINE_HEIGHT + 24;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value]);

  // Si nos llega initialValue después del montaje, lo aplicamos y
  // ponemos el cursor al final.
  useEffect(() => {
    if (initialValue === undefined) return;
    setValue(initialValue);
    // Esperar al repintado antes de mover el cursor
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [initialValue]);

  // Ctrl+V: capturar archivos o imágenes del portapapeles
  useEffect(() => {
    const attachFn = onAttach;
    if (!attachFn) return;

    function handlePaste(e: ClipboardEvent) {
      if (attachment) return;
      const items = e.clipboardData?.items;
      if (!items) return;

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) {
            e.preventDefault();
            attachFn?.(file);
            return;
          }
        }
      }
    }

    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [onAttach, attachment]);

  const isAttachmentPending =
    !!attachment &&
    (attachment.status === "uploading" ||
      attachment.status === "processing");

  function submit() {
    const trimmed = value.trim();
    if (disabled || streaming) return;
    if (!trimmed && !attachment) return;
    onSend(trimmed);
    setValue("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && onAttach) onAttach(file);
    e.target.value = "";
  }

  const canSend =
    !disabled && !streaming && (value.trim().length > 0 || !!attachment);

  return (
    <div className="border-t border-[var(--color-border)] bg-[var(--color-background)] p-4">
      {attachment && onRemoveAttachment && (
        <ChatAttachment
          attachment={attachment}
          onRemove={onRemoveAttachment}
        />
      )}

      {isAttachmentPending && (
        <p className="mx-auto mb-2 flex max-w-3xl items-center justify-center gap-1.5 text-xs text-[var(--color-muted)]">
          <AlertCircle className="h-3 w-3" />
          El archivo aún se está procesando. Si envías ahora, ELI responderá
          sin leerlo.
        </p>
      )}

      {attachment && attachment.status === "failed" && (
        <p className="mx-auto mb-2 flex max-w-3xl items-center justify-center gap-1.5 text-xs text-[var(--color-danger)]">
          <AlertCircle className="h-3 w-3" />
          El archivo no se procesó. Envíalo de nuevo o quítalo con la X.
        </p>
      )}

      <div
  className={cn(
    "surface-elevated mx-auto flex max-w-3xl items-end gap-1 rounded-[26px] py-1.5 pl-1.5 pr-2 transition-soft focus-within:border-[var(--color-primary)]/40 md:gap-2 md:py-2 md:pl-2 md:pr-2.5",
  )}
>
        {onAttach && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || streaming || !!attachment}
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
              "text-[var(--color-subtle)] transition-colors",
              "hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
              "disabled:cursor-not-allowed disabled:opacity-40",
            )}
            aria-label="Adjuntar archivo"
            title="Adjuntar archivo (arrastra, pega o haz click)"
          >
            <Paperclip className="h-4 w-4" />
          </button>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_ATTR}
          className="hidden"
          onChange={handleFileChange}
        />

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
            disabled={!canSend}
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
              "transition-colors",
              canSend
                ? "bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)]"
                : "bg-[var(--color-surface-hover)] text-[var(--color-subtle)] cursor-not-allowed",
            )}
            aria-label="Enviar"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>

     <p className="mx-auto mt-2 hidden max-w-3xl text-center text-[11px] text-[var(--color-subtle)] md:block">
  <kbd className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-1 py-0.5 font-mono text-[10px]">Enter</kbd> enviar ·
  <kbd className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-1 py-0.5 font-mono text-[10px]">Shift+Enter</kbd> nueva línea ·
  <kbd className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-1 py-0.5 font-mono text-[10px]">Ctrl+V</kbd> adjuntar
</p>
    </div>
  );
}