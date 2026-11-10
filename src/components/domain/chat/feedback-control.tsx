"use client";

import { useState } from "react";
import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";

export type FeedbackValue = "helpful" | "not_helpful";

const REASONS = ["Not accurate", "Hard to follow", "Missing information"];

interface FeedbackControlProps {
  value?: FeedbackValue;
  reason?: string;
  onChange: (value: FeedbackValue, reason?: string) => void;
  /** Shown while an answer is still streaming in later phases. */
  disabled?: boolean;
}

/**
 * Per-answer feedback: quiet prompt → one click → optional reason on
 * negative → recorded state. Small and unobtrusive by design.
 */
export function FeedbackControl({ value, reason, onChange, disabled }: FeedbackControlProps) {
  const [awaitingReason, setAwaitingReason] = useState(false);

  if (value === "helpful") {
    return (
      <p className="flex items-center gap-1.5 text-[11px] text-ink-muted animate-fade-in">
        <Check aria-hidden="true" className="size-3.5 text-success" />
        Thanks — marked helpful
      </p>
    );
  }

  if (value === "not_helpful") {
    return (
      <p className="text-[11px] text-ink-muted animate-fade-in">
        Recorded{reason ? ` — ${reason.toLowerCase()}` : ""} — thanks, it helps improve the
        knowledge base
      </p>
    );
  }

  if (awaitingReason) {
    return (
      <div className="flex flex-wrap items-center gap-1.5 animate-fade-in">
        <span className="text-[11px] text-ink-muted">What was off?</span>
        {REASONS.map((option) => (
          <button
            key={option}
            type="button"
            disabled={disabled}
            onClick={() => {
              setAwaitingReason(false);
              onChange("not_helpful", option);
            }}
            className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-ink-secondary transition-colors duration-fast hover:border-line-strong hover:text-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
          >
            {option}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-ink-muted">Helpful?</span>
      <button
        type="button"
        aria-label="Mark this answer helpful"
        disabled={disabled}
        onClick={() => onChange("helpful")}
        className="rounded-control p-1.5 text-ink-muted transition-all duration-fast hover:-translate-y-px hover:bg-surface-2 hover:text-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
      >
        <ThumbsUp aria-hidden="true" className="size-3.5" />
      </button>
      <button
        type="button"
        aria-label="Mark this answer not helpful"
        disabled={disabled}
        onClick={() => setAwaitingReason(true)}
        className={cn(
          "rounded-control p-1.5 text-ink-muted transition-all duration-fast hover:-translate-y-px hover:bg-surface-2 hover:text-ink",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
        )}
      >
        <ThumbsDown aria-hidden="true" className="size-3.5" />
      </button>
    </div>
  );
}
