"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "@/lib/api/types";

interface ChatState {
  messages: Message[];
  streaming: boolean;
  error: string | null;
}

type ServerEvent =
  | {
      type: "meta";
      request_id: string;
      conversation_id: string;
      user_message_id: string;
      route: string;
    }
  | { type: "token"; delta: string }
  | { type: "plan_created"; goal: string; steps: unknown[] }
  | { type: "plan_executed"; status: string; steps: unknown[] }
  | { type: "goal_created"; goal_id: string; kind: string; content: string }
  | {
      type: "final";
      assistant_message_id: string;
      usage: Record<string, number>;
    }
  | { type: "error"; message: string };

export function useChat(conversationId: string | null) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    streaming: false,
    error: null,
  });
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(conversationId);

  const abortRef = useRef<AbortController | null>(null);
  const tempIdsRef = useRef<{ user: string | null; assistant: string | null }>(
    { user: null, assistant: null },
  );

  // Sincronizar el estado interno con la prop cuando navegamos
  // a otra conversación (o cuando pasamos de /chat a /chat/[id]).
  useEffect(() => {
    setActiveConversationId(conversationId);
  }, [conversationId]);

  // Cargar mensajes desde el backend SOLO cuando cambia la prop
  // (es decir, al navegar a una conversación existente).
  // NO dependemos del estado interno para no interferir con el stream:
  // cuando el backend crea una nueva conversación, el evento "meta"
  // actualiza activeConversationId, pero los mensajes ya están en el estado
  // local y no deben ser reemplazados.
  useEffect(() => {
    if (!conversationId) return;

    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(
          `/api/v1/conversations/${conversationId}/messages`,
          { credentials: "include" },
        );
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = (await r.json()) as Message[];
        if (cancelled) return;
        setState((s) => ({ ...s, messages: data, error: null }));
      } catch (err) {
        if (cancelled) return;
        setState((s) => ({ ...s, error: (err as Error).message }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const send = useCallback(
    async (text: string, attachedDocumentIds: string[] = []) => {
      if (state.streaming) return;

      const now = Date.now();
      const tempUserId = `temp-user-${now}`;
      const tempAssistantId = `temp-assistant-${now}`;
      tempIdsRef.current = { user: tempUserId, assistant: tempAssistantId };

      const tempUser: Message = {
        id: tempUserId,
        conversation_id: activeConversationId ?? "",
        role: "user",
        content: text,
        tokens_in: 0,
        tokens_out: 0,
        model: null,
        created_at: new Date().toISOString(),
      };
      const tempAssistant: Message = {
        id: tempAssistantId,
        conversation_id: activeConversationId ?? "",
        role: "assistant",
        content: "",
        tokens_in: 0,
        tokens_out: 0,
        model: null,
        created_at: new Date().toISOString(),
      };

      setState((s) => ({
        messages: [...s.messages, tempUser, tempAssistant],
        streaming: true,
        error: null,
      }));

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const r = await fetch("/api/v1/chat", {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            conversation_id: activeConversationId ?? null,
            message: text,
            attached_document_ids: attachedDocumentIds,
          }),
          signal: controller.signal,
        });

        if (!r.ok || !r.body) {
          throw new Error(`HTTP ${r.status}`);
        }

        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            const json = line.slice(5).trim();
            if (!json) continue;

            let ev: ServerEvent;
            try {
              ev = JSON.parse(json);
            } catch {
              continue;
            }
            applyEvent(ev);
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          // cancelado por el usuario
        } else {
          setState((s) => ({ ...s, error: (err as Error).message }));
        }
      } finally {
        abortRef.current = null;
        setState((s) => ({ ...s, streaming: false }));
        tempIdsRef.current = { user: null, assistant: null };
      }
    },
    [activeConversationId, state.streaming],
  );

  function applyEvent(ev: ServerEvent) {
    switch (ev.type) {
      case "meta": {
        setActiveConversationId(ev.conversation_id);
        setState((s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === tempIdsRef.current.user
              ? {
                  ...m,
                  id: ev.user_message_id,
                  conversation_id: ev.conversation_id,
                }
              : m,
          ),
        }));
        break;
      }
      case "token": {
        setState((s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === tempIdsRef.current.assistant
              ? { ...m, content: m.content + ev.delta }
              : m,
          ),
        }));
        break;
      }
      case "final": {
        setState((s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === tempIdsRef.current.assistant
              ? { ...m, id: ev.assistant_message_id }
              : m,
          ),
        }));
        break;
      }
      case "error": {
        setState((s) => ({ ...s, error: ev.message }));
        break;
      }
      default:
        break;
    }
  }

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    state,
    send,
    cancelStream,
    conversationId: activeConversationId,
  };
}