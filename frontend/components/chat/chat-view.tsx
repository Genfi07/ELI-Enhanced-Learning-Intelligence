"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  Sparkles,
  FileText,
  UploadCloud,
  Brain,
  Wrench,
} from "lucide-react";
import { MessageBubble } from "./message-bubble";
import { ChatInput } from "./chat-input";
import { useAttachment } from "@/lib/hooks/use-attachment";
import { useNewChatStore } from "@/lib/stores/new-chat-store";
import type { useChat } from "@/lib/hooks/use-chat";

interface ChatViewProps {
  chat: ReturnType<typeof useChat>;
  title?: string;
}

export function ChatView({ chat, title }: ChatViewProps) {
  const { state, send, cancelStream } = chat;
  const scrollRef = useRef<HTMLDivElement>(null);
  const { attachment, attach, clear } = useAttachment();

  const consumePrompt = useNewChatStore((s) => s.consumePrompt);
  const [initialPrompt, setInitialPrompt] = useState<string | undefined>(
    undefined,
  );
  useEffect(() => {
    const p = consumePrompt();
    if (p) setInitialPrompt(p);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [dragging, setDragging] = useState(false);
  const dragCounterRef = useRef(0);

  const [proactiveNotice, setProactiveNotice] = useState<{
    fileName: string;
    chunkCount: number;
    docId: string;
  } | null>(null);

  const lastReadyRef = useRef<string | null>(null);
  useEffect(() => {
    if (
      attachment?.status === "ready" &&
      attachment.docId &&
      lastReadyRef.current !== attachment.docId
    ) {
      lastReadyRef.current = attachment.docId;
      setProactiveNotice({
        fileName: attachment.fileName,
        chunkCount: attachment.chunkCount ?? 0,
        docId: attachment.docId,
      });
    }
    if (!attachment) {
      lastReadyRef.current = null;
    }
  }, [attachment]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [state.messages, proactiveNotice]);

  const canAcceptDrop = !attachment && !state.streaming;

  function onDragEnter(e: React.DragEvent<HTMLDivElement>) {
    if (!canAcceptDrop) return;
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) setDragging(true);
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    if (!canAcceptDrop) return;
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    if (!canAcceptDrop) return;
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setDragging(false);
    }
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDragging(false);
    if (!canAcceptDrop) return;
    const file = e.dataTransfer.files?.[0];
    if (file) attach(file);
  }

  function handleSend(text: string) {
    const attachedIds =
      attachment?.status === "ready" && attachment.docId
        ? [attachment.docId]
        : [];

    send(text, attachedIds);
    setProactiveNotice(null);
    setInitialPrompt(undefined);

    if (attachedIds.length > 0) {
      clear();
    }
  }

  const isEmpty = state.messages.length === 0;

  // Cuando el backend crea una nueva conversación, actualizamos la URL
  // sin remontar el componente para no perder el estado local.
  useEffect(() => {
    if (!chat.conversationId) return;
    if (title) return;
    const target = `/chat/${chat.conversationId}`;
    if (window.location.pathname === target) return;
    window.history.replaceState(null, "", target);
  }, [chat.conversationId, title]);

  return (
    <div
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className="relative flex flex-1 flex-col overflow-hidden"
    >
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isEmpty && !proactiveNotice ? (
          <EmptyState />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col py-2 md:py-4">
            {state.messages.map((m, i) => {
              const isLast = i === state.messages.length - 1;
              const streamingThisOne =
                state.streaming && isLast && m.role === "assistant";
              return (
                <MessageBubble
                  key={m.id}
                  role={m.role === "user" ? "user" : "assistant"}
                  content={m.content}
                  streaming={streamingThisOne}
                />
              );
            })}

            {proactiveNotice && (
              <div className="flex w-full justify-start gap-2 px-3 py-2 md:gap-3 md:px-4 md:py-4">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2 text-sm text-[var(--color-foreground)] md:max-w-[min(720px,80%)] md:px-4 md:py-2.5">
                  <p>
                    He recibido <strong>{proactiveNotice.fileName}</strong>.
                    {proactiveNotice.chunkCount > 0 && (
                      <>
                        {" "}
                        Lo he dividido en {proactiveNotice.chunkCount}{" "}
                        fragmentos y ya lo tengo presente.
                      </>
                    )}{" "}
                    ¿Qué quieres que haga con él?
                  </p>
                  <p className="mt-1.5 text-xs text-[var(--color-subtle)]">
                    Escríbeme qué necesitas: resumirlo, buscar algo concreto,
                    comparar secciones, extraer datos…
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {state.error && (
        <div className="mx-3 mt-2 flex max-w-3xl items-start gap-2 rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)] md:mx-auto">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{state.error}</span>
        </div>
      )}

      <ChatInput
        onSend={handleSend}
        onCancel={cancelStream}
        onAttach={attach}
        onRemoveAttachment={clear}
        attachment={attachment}
        streaming={state.streaming}
        initialValue={initialPrompt}
        placeholder={
          title ? `Continúa la conversación…` : "Pregúntale algo a ELI…"
        }
      />

      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-[var(--color-primary)] bg-[var(--color-surface)] px-8 py-8 shadow-2xl md:px-12 md:py-10">
            <UploadCloud className="h-12 w-12 text-[var(--color-primary)]" />
            <p className="text-lg font-semibold text-[var(--color-foreground)]">
              Suelta el archivo aquí
            </p>
            <p className="text-sm text-[var(--color-muted)]">
              PDF, DOCX, XLSX, TXT, MD, CSV o JSON
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col justify-end px-4 pb-2 md:justify-center md:pb-0">
      <div className="mx-auto w-full max-w-md">
        <div className="mb-5 flex flex-col items-center text-center md:items-start md:text-left">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
            <Sparkles className="h-5 w-5" />
          </div>
          <h2 className="mt-3 text-lg font-semibold">¿En qué te ayudo hoy?</h2>
        </div>

        <div className="space-y-1.5">
          <QuickAction
            href="/files"
            icon={<FileText className="h-3.5 w-3.5" />}
            label="Subir un documento"
          />
          <QuickAction
            href="/memory"
            icon={<Brain className="h-3.5 w-3.5" />}
            label="Repasar mi memoria"
          />
          <QuickAction
            href="/tools"
            icon={<Wrench className="h-3.5 w-3.5" />}
            label="Usar una herramienta"
          />
        </div>
      </div>
    </div>
  );
}

function QuickAction({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex w-full items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-left transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-hover)] active:scale-[0.99]"
    >
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
        {icon}
      </div>
      <span className="truncate text-sm text-[var(--color-foreground)]">
        {label}
      </span>
    </Link>
  );
}