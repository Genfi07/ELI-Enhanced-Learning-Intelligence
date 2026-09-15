"use client";

import { useEffect, useRef } from "react";
import { AlertCircle, Sparkles } from "lucide-react";
import { MessageBubble } from "./message-bubble";
import { ChatInput } from "./chat-input";
import { useAttachment } from "@/lib/hooks/use-attachment";
import type { useChat } from "@/lib/hooks/use-chat";

interface ChatViewProps {
  chat: ReturnType<typeof useChat>;
  title?: string;
}

export function ChatView({ chat, title }: ChatViewProps) {
  const { state, send, cancelStream } = chat;
  const scrollRef = useRef<HTMLDivElement>(null);
  const { attachment, attach, clear } = useAttachment();

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [state.messages]);

  function handleSend(text: string) {
    const attachedIds =
      attachment?.status === "ready" && attachment.docId
        ? [attachment.docId]
        : [];

    send(text, attachedIds);

    // Limpiamos el chip tras enviar. El archivo sigue vivo en /files
    // para que el usuario lo pueda ver y gestionar.
    if (attachedIds.length > 0) {
      clear();
    }
  }

  const isEmpty = state.messages.length === 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isEmpty ? (
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
        placeholder={
          title ? `Continúa la conversación…` : "Pregúntale algo a ELI…"
        }
      />
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
          Puedes adjuntar un PDF, Word, Excel o imagen con el clip 📎
        </p>
      </div>
    </div>
  );
}