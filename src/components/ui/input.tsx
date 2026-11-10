"use client";

import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";
import { useFieldContext } from "./field";

export type InputProps = ComponentPropsWithoutRef<"input">;

/**
 * Single-line text control. Inherits id/hint/error from a parent <Field>
 * when present; also works standalone.
 */
export function Input({
  className,
  id,
  "aria-describedby": ariaDescribedBy,
  ...props
}: InputProps) {
  const field = useFieldContext();
  const invalid = field?.invalid ?? false;

  return (
    <input
      id={id ?? field?.id}
      aria-describedby={ariaDescribedBy ?? field?.describedBy}
      aria-invalid={invalid || undefined}
      className={cn(
        "h-9 w-full rounded-control border bg-surface-2 px-3 text-sm text-ink placeholder:text-ink-muted transition-[border-color,box-shadow] duration-fast focus:outline-hidden",
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
