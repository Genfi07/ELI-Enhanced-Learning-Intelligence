"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Bot, User as UserIcon, Paperclip } from "lucide-react";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  attachmentName?: string | null;
}

export function MessageBubble({
  role,
  content,
  streaming,
  attachmentName,
}: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div
      className={cn(
        "group flex w-full gap-2 px-3 py-1.5 md:gap-3 md:px-4 md:py-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="mt-0.5 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)] md:flex">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm shadow-sm md:max-w-[min(720px,80%)] md:px-4 md:py-2.5",
          isUser
            ? "rounded-br-md bg-[var(--color-primary)] text-white"
            : "rounded-bl-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-foreground)]",
        )}
      >
        {isUser && attachmentName && (
          <div className="mb-2 inline-flex items-center gap-1.5 rounded bg-white/15 px-2 py-1 text-xs">
            <Paperclip className="h-3 w-3" />
            <span className="max-w-[280px] truncate">{attachmentName}</span>
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap break-words leading-relaxed">
            {content}
          </p>
        ) : (
          <div className="prose-eli break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
            >
              {content}
            </ReactMarkdown>
            {streaming && <span className="cursor-blink ml-0.5" />}
          </div>
        )}
      </div>

      {isUser && (
        <div className="mt-0.5 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-[var(--color-muted)] md:flex">
          <UserIcon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}
