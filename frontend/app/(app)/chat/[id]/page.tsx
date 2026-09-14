"use client";

import { use } from "react";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useChat } from "@/lib/hooks/use-chat";
import { Header } from "@/components/layout/header";
import { ChatView } from "@/components/chat/chat-view";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ConversationPage({ params }: PageProps) {
  const { id } = use(params);
  const { data: user } = useCurrentUser();
  const chat = useChat(id);

  if (!user) return null;

  return (
    <>
      <Header title="Chat" user={user} />
      <ChatView chat={chat} title="Conversación" />
    </>
  );
}