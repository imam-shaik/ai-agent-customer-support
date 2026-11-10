"use client";

import { LogoMark } from "@/components/brand/Logo";
import { Skeleton } from "@/components/ui/skeleton";
import { THINKING_DETAIL, THINKING_HEADING } from "@/lib/support/thinking";

/**
 * Loading state while the real turn runs: the assistant identity row
 * plus an answer-shaped shimmer skeleton. Honest by design — no stage
 * claims, no artificial delays; it unmounts the moment the response
 * arrives.
 */
export function ThinkingIndicator() {
  return (
    <div role="status" aria-live="polite" className="animate-fade-in">
      <div className="mb-3 flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-control border border-accent-border bg-accent-soft"
        >
          <LogoMark className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{THINKING_HEADING}</p>
          <p className="truncate text-xs text-ink-muted">{THINKING_DETAIL}</p>
        </div>
      </div>

      {/* Answer-shaped skeleton: prose lines + trust row, not a stage list */}
      <div className="ml-0 space-y-3 md:ml-11" aria-hidden="true">
        <Skeleton className="h-4 w-[92%]" />
        <Skeleton className="h-4 w-[85%]" />
        <Skeleton className="h-4 w-[60%]" />
        <div className="flex items-center gap-2 pt-1.5">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      </div>
    </div>
  );
}
