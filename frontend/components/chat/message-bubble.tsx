"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Bot, User as UserIcon, Paperclip } from "lucide-react";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  /** Si true, muestra un cursor parpadeante al final (streaming en curso). */
  streaming?: boolean;
  /** Nombre del archivo adjunto a este mensaje (solo para role=user). */
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
        "group flex w-full gap-3 px-4 py-4",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div
        className={cn(
          "max-w-[min(720px,80%)] rounded-lg px-4 py-2.5 text-sm",
          isUser
            ? "bg-[var(--color-primary)] text-white"
            : "bg-[var(--color-surface)] text-[var(--color-foreground)]",
        )}
      >
        {/* Chip del adjunto (solo user) */}
        {isUser && attachmentName && (
          <div className="mb-2 inline-flex items-center gap-1.5 rounded bg-white/15 px-2 py-1 text-xs">
            <Paperclip className="h-3 w-3" />
            <span className="truncate max-w-[280px]">{attachmentName}</span>
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
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-[var(--color-muted)]">
          <UserIcon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}