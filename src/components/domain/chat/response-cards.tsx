"use client";

import { useState } from "react";
import { CircleSlash2, PencilLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ---------- Clarifying question ---------- */

interface ClarifyingCardProps {
  text: string;
  options: string[];
  onPick: (question: string) => void;
}

export function ClarifyingCard({ text, options, onPick }: ClarifyingCardProps) {
  const [picked, setPicked] = useState<string | null>(null);

  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">{text}</p>
      {picked ? (
        <p className="mt-3 flex items-center gap-1.5 text-[13px] text-ink-muted animate-fade-in">
          <span className="font-medium text-ink-secondary">You answered:</span> {picked} — working
          on it below.
        </p>
      ) : (
        <ul className="mt-3.5 flex flex-wrap gap-2">
          {options.map((option) => (
            <li key={option}>
              <button
                type="button"
                onClick={() => {
                  setPicked(option);
                  onPick(option);
                }}
                className={cn(
                  "rounded-control border border-line bg-surface-2 px-3.5 py-2 text-left text-sm text-ink",
                  "transition-all duration-fast hover:-translate-y-px hover:border-line-strong hover:bg-surface-3",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 active:translate-y-0",
                )}
              >
                {option}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------- Prompt-injection guard ---------- */

interface GuardCardProps {
  text: string;
  options: string[];
  onPick: (question: string) => void;
}

/**
 * Injection-style message outcome: rules held, nothing internal was
 * revealed, and the normal support workflow continues.
 */
export function GuardCard({ text, options, onPick }: GuardCardProps) {
  const [picked, setPicked] = useState<string | null>(null);

  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">{text}</p>
      {picked ? (
        <p className="mt-3.5 flex items-center gap-1.5 text-[13px] text-ink-muted animate-fade-in">
          <span className="font-medium text-ink-secondary">You answered:</span> {picked} — working
          on it below.
        </p>
      ) : (
        <ul className="mt-3.5 flex flex-wrap gap-2">
          {options.map((option) => (
            <li key={option}>
              <button
                type="button"
                onClick={() => {
                  setPicked(option);
                  onPick(option);
                }}
                className={cn(
                  "rounded-control border border-line bg-surface-2 px-3.5 py-2 text-left text-sm text-ink",
                  "transition-all duration-fast hover:-translate-y-px hover:border-line-strong hover:bg-surface-3",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 active:translate-y-0",
                )}
              >
                {option}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------- Unsupported / insufficient evidence / conflict ---------- */

interface FallbackCardProps {
  text: string;
  checkedDocIds: string[];
  suggestions: string[];
  /** Heading override (e.g. conflicting-evidence wording). */
  title?: string;
  escalationOffer?: string | null;
  documentTitles?: Record<string, string>;
  ticketId?: string;
  onEscalate: () => void;
  onPick: (question: string) => void;
}

export function FallbackCard({
  text,
  checkedDocIds,
  suggestions,
  title = "I couldn't confirm an answer",
  escalationOffer,
  documentTitles,
  ticketId,
  onEscalate,
  onPick,
}: FallbackCardProps) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">{title}</p>
      <p className="mt-1.5 max-w-[65ch] text-[15px] leading-relaxed text-ink">{text}</p>

      {checkedDocIds.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[11px] text-ink-muted">
          <span className="font-medium uppercase tracking-wide">Looked in:</span>
          {checkedDocIds.map((docId) => {
            const label = documentTitles?.[docId] ?? docId;
            return (
              <span
                key={docId}
                title={docId}
                className="max-w-full truncate rounded-full border border-line bg-surface-2 px-2 py-0.5"
              >
                {label}
              </span>
            );
          })}
        </p>
      )}

      {escalationOffer && (
        <p className="mt-3 max-w-[65ch] border-l-2 border-line-strong pl-3 text-[13px] leading-relaxed text-ink-secondary">
          {escalationOffer}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={onEscalate}>
          {ticketId ? `View ticket ${ticketId}` : "Contact Support Team"}
        </Button>
        <span className="text-[11px] text-ink-muted">Your conversation will be attached</span>
      </div>

      {suggestions.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
            Try asking instead
          </p>
          <ul className="mt-1.5 flex flex-col">
            {suggestions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => onPick(question)}
                  className={cn(
                    "group flex w-full items-center justify-between gap-3 rounded-control px-2 py-1.5 text-left text-[13px] text-ink-secondary",
                    "transition-colors duration-fast hover:bg-surface-2 hover:text-ink",
                    "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                  )}
                >
                  <span>{question}</span>
                  <span
                    aria-hidden="true"
                    className="text-ink-muted transition-all duration-fast group-hover:translate-x-0.5 group-hover:text-accent-ink"
                  >
                    →
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ---------- Escalation offer ---------- */

interface EscalationOfferCardProps {
  text: string;
  ticketId?: string;
  onEscalate: () => void;
}

export function EscalationOfferCard({ text, ticketId, onEscalate }: EscalationOfferCardProps) {
  return (
    <div className="min-w-0">
      <p className="text-[15px] leading-relaxed text-ink">{text}</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={onEscalate}>
          {ticketId ? `View ticket ${ticketId}` : "Contact Support Team"}
        </Button>
        <span className="text-[11px] text-ink-muted">
          Reviewed by a person, usually within one business day
        </span>
      </div>
    </div>
  );
}

/* ---------- API failure + retry ---------- */

interface ErrorRetryCardProps {
  text: string;
  onRetry?: () => void;
}

export function ErrorRetryCard({ text, onRetry }: ErrorRetryCardProps) {
  return (
    <div role="alert" className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
        The support service didn't respond
      </p>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink">{text}</p>
      <div className="mt-3.5 flex flex-wrap items-center gap-3">
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
        <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
          Nothing was sent twice — retry re-runs your last message.
        </p>
      </div>
    </div>
  );
}

/* ---------- User-cancelled turn (Esc / Stop) ---------- */

interface CancelledCardProps {
  /** Resend with the SAME request id: replays a completed turn, never duplicates. */
  onRetry: () => void;
  /** Load the original wording into the composer for a corrected resend. */
  onEdit?: () => void;
}

/**
 * The customer stopped waiting (Esc / Stop). The backend turn may still
 * complete and persist — "Try again" replays it idempotently instead of
 * creating a duplicate, and "Edit message" rephrases the question as a
 * new turn (history stays append-only and honest).
 */
export function CancelledCard({ onRetry, onEdit }: CancelledCardProps) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
        Cancelled
      </p>
      <p className="mt-1.5 max-w-[65ch] text-[15px] leading-relaxed text-ink">
        You stopped waiting for this response. Your message is kept — the
        answer may still finish, and trying again loads it instead of sending
        anything twice.
      </p>
      <div className="mt-3.5 flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
        {onEdit && (
          <Button variant="ghost" size="sm" onClick={onEdit}>
            <PencilLine aria-hidden="true" className="size-3.5" />
            Edit message
          </Button>
        )}
      </div>
    </div>
  );
}
