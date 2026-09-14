"use client";

import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useChat } from "@/lib/hooks/use-chat";
import { Header } from "@/components/layout/header";
import { ChatView } from "@/components/chat/chat-view";
import { useNewChatStore } from "@/lib/stores/new-chat-store";

export default function ChatPage() {
  const { data: user } = useCurrentUser();
  const chat = useChat(null);
  // La key fuerza un remount cuando el usuario pulsa "Nuevo chat"
  // estando ya en /chat (donde un Link no resetearía el estado).
  const newChatKey = useNewChatStore((s) => s.key);

  if (!user) return null;

  return (
    <>
      <Header title="Chat" user={user} />
      <ChatView key={newChatKey} chat={chat} />
    </>
  );
}