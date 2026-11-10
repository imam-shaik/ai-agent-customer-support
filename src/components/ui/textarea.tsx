"use client";

import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";
import { useFieldContext } from "./field";

export type TextareaProps = ComponentPropsWithoutRef<"textarea">;

/**
 * Multi-line text control (notes, message composition, summaries).
 * Resizable vertically; grows naturally with content.
 */
export function Textarea({
  className,
  id,
  "aria-describedby": ariaDescribedBy,
  ...props
}: TextareaProps) {
  const field = useFieldContext();
  const invalid = field?.invalid ?? false;

  return (
    <textarea
      id={id ?? field?.id}
      aria-describedby={ariaDescribedBy ?? field?.describedBy}
      aria-invalid={invalid || undefined}
      className={cn(
        "min-h-24 w-full resize-y rounded-control border bg-surface-2 px-3 py-2.5 text-sm leading-relaxed text-ink placeholder:text-ink-muted transition-[border-color,box-shadow] duration-fast focus:outline-hidden",
        invalid
          ? "border-danger-border focus:border-danger focus:ring-2 focus:ring-danger/30"
          : "border-line hover:border-line-strong focus:border-accent-border focus:ring-2 focus:ring-accent/40",
        "disabled:cursor-not-allowed disabled:opacity-50 read-only:bg-surface-1 read-only:text-ink-secondary",
        className
      )}
      {...props}
    />
  );
}
