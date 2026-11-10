import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  /** Single primary action — the one thing to do next. */
  action?: ReactNode;
  secondaryAction?: ReactNode;
  className?: string;
}

/**
 * Designed absence: says what's empty, why that's okay, and what to do.
 * Use inside Cards or as a page-level state.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center px-6 py-12 text-center",
        className
      )}
    >
      <div
        aria-hidden="true"
        className="mb-4 flex size-11 items-center justify-center rounded-card border border-line bg-surface-2 text-ink-muted"
      >
        {icon ?? <Inbox className="size-5" />}
      </div>
      <p className="font-display text-[15px] font-semibold tracking-tight text-ink">
        {title}
      </p>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-secondary">
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
