"use client";

import type { ComponentPropsWithoutRef } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFieldContext } from "./field";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps extends Omit<ComponentPropsWithoutRef<"select">, "children"> {
  options: SelectOption[];
  /** Empty-value first option, e.g. "All statuses". */
  placeholder?: string;
}

/**
 * Native select in a styled shell (reliable on mobile, free a11y).
 * Use for short option lists — filters, statuses, reasons.
 */
export function Select({
  options,
  placeholder,
  className,
  id,
  "aria-describedby": ariaDescribedBy,
  ...props
}: SelectProps) {
  const field = useFieldContext();
  const invalid = field?.invalid ?? false;

  return (
    <div className="relative">
      <select
        id={id ?? field?.id}
        aria-describedby={ariaDescribedBy ?? field?.describedBy}
        aria-invalid={invalid || undefined}
        className={cn(
          "h-9 w-full appearance-none rounded-control border bg-surface-2 py-0 pl-3 pr-9 text-sm text-ink transition-[border-color,box-shadow] duration-fast focus:outline-hidden",
          invalid
            ? "border-danger-border focus:border-danger focus:ring-2 focus:ring-danger/30"
            : "border-line hover:border-line-strong focus:border-accent-border focus:ring-2 focus:ring-accent/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
            className="bg-surface-2 text-ink"
          >
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted"
      />
    </div>
  );
}
