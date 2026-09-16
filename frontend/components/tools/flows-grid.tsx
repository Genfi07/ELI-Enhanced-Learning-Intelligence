"use client";

import { useRouter } from "next/navigation";
import { FlowCard } from "./flow-card";
import { FLOWS } from "@/lib/constants/flows";
import { useNewChatStore } from "@/lib/stores/new-chat-store";

export function FlowsGrid() {
  const router = useRouter();
  const prefill = useNewChatStore((s) => s.prefill);

  function useFlow(prompt: string) {
    prefill(prompt);
    router.push("/chat");
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {FLOWS.map((flow) => (
        <FlowCard
          key={flow.id}
          flow={flow}
          onUse={() => useFlow(flow.prompt)}
        />
      ))}
    </div>
  );
}