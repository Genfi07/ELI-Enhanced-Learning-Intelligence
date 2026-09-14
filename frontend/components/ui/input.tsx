import { cn } from "@/lib/utils";
import { forwardRef, type InputHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "w-full rounded-md border border-[var(--color-border-strong)] " +
            "bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-foreground)] " +
            "placeholder:text-[var(--color-subtle)] " +
            "transition-colors focus:border-[var(--color-primary)] focus:outline-none " +
            "disabled:opacity-50 disabled:cursor-not-allowed",
          className,
        )}
        {...props}
      />
    );
  },
);