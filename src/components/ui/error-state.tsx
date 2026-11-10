import type { ReactNode } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  description?: string;
  /** Renders a retry action when provided. */
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
  className?: string;
}

/**
 * Recoverable failure: says what happened, keeps the user's context,
 * offers the way forward. Never a dead end.
 */
export function ErrorState({
  title = "Something went wrong",
  description = "We couldn't complete that request. Your place is saved — try again.",
  onRetry,
  retryLabel = "Try again",
  action,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center px-6 py-12 text-center",
        className
      )}
    >
      <div
        aria-hidden="true"
        className="mb-4 flex size-11 items-center justify-center rounded-card border border-danger-border bg-danger-soft text-danger-ink"
      >
        <TriangleAlert className="size-5" />
      </div>
      <p className="font-display text-[15px] font-semibold tracking-tight text-ink">
        {title}
      </p>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-secondary">
        {description}
      </p>
      {(onRetry || action) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}
