"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Sparkles, FileText, UploadCloud } from "lucide-react";
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

  // Prompt precargado desde /tools → flujos
  const consumePrompt = useNewChatStore((s) => s.consumePrompt);
  const [initialPrompt, setInitialPrompt] = useState<string | undefined>(
    undefined,
  );
  useEffect(() => {
    const p = consumePrompt();
    if (p) setInitialPrompt(p);
    // Se ejecuta solo al montar
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Estado del drag & drop a nivel de chat completo
  const [dragging, setDragging] = useState(false);
  const dragCounterRef = useRef(0);

  // Aviso proactivo: cuando el chip pasa a READY, mostramos un mensaje
  // de ELI invitando a preguntar sobre el archivo.
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

  // ------------------------------------------------------------------ //
  // Drag & drop global del chat
  // ------------------------------------------------------------------ //
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
          <div className="mx-auto flex max-w-3xl flex-col py-4">
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
              <div className="flex w-full justify-start gap-3 px-4 py-4">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="max-w-[min(720px,80%)] rounded-lg bg-[var(--color-surface)] px-4 py-2.5 text-sm text-[var(--color-foreground)]">
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
        <div className="mx-auto mt-2 flex max-w-3xl items-start gap-2 rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">
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

      {/* Overlay global de drop */}
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-[var(--color-primary)] bg-[var(--color-surface)] px-12 py-10 shadow-2xl">
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
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-md text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
          <Sparkles className="h-5 w-5" />
        </div>
        <h2 className="mt-4 text-xl font-semibold">¿En qué te ayudo hoy?</h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          ELI recuerda lo que le cuentas, lee tus documentos, planifica tareas
          complejas y usa herramientas cuando hace falta.
        </p>
        <p className="mt-3 text-xs text-[var(--color-subtle)]">
          Arrastra un PDF, Word, Excel o imagen al chat, o pégalo con Ctrl+V.
        </p>
      </div>
    </div>
  );
}