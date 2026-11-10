"use client";

import { Fragment } from "react";
import { Pencil, Square } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GroundedAnswer } from "./grounded-answer";
import {
  CancelledCard,
  ClarifyingCard,
  ErrorRetryCard,
  EscalationOfferCard,
  FallbackCard,
  GuardCard,
} from "./response-cards";
import { ThinkingIndicator } from "./thinking-indicator";
import { FeedbackControl, type FeedbackValue } from "./feedback-control";

export type { FeedbackValue };
import type { ApiCitation, AgentReply } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export interface FeedbackState {
  value: FeedbackValue;
  reason?: string;
}

export type ChatMessage =
  | {
      id: string;
      kind: "user";
      text: string;
      time: string;
      createdAt?: string;
      clientRequestId?: string | null;
    }
  | {
      id: string;
      kind: "agent";
      reply: AgentReply;
      time: string;
      createdAt?: string;
      feedback?: FeedbackState;
      /** Present on error cards: the exact turn to retry idempotently. */
      failedTurn?: { content: string; clientRequestId: string | null };
      /** True when the CUSTOMER cancelled the wait (Esc / Stop) — renders
       *  the calm cancelled card instead of a failure alert. */
      cancelled?: boolean;
    }
  | { id: string; kind: "system"; text: string; ticketId?: string; time: string };

interface MessageTimelineProps {
  messages: ChatMessage[];
  /** True while the real request is in flight (presentational only). */
  thinking: boolean;
  ticketId?: string;
  documentTitles?: Record<string, string>;
  onFeedback: (id: string, value: FeedbackValue, reason?: string) => void;
  onRetry: (messageId: string) => void;
  onEscalate: () => void;
  onPick: (question: string) => void;
  onOpenTicket: () => void;
  /** Opens the evidence sheet with one answer's stored citations. */
  onInspectEvidence?: (citations: ApiCitation[], context: string) => void;
  /** Stops WAITING for the in-flight response (Esc / Stop button). */
  onStop?: () => void;
  /** Prefills the composer with a previous question for a corrected resend. */
  onEditQuery?: (text: string) => void;
}

export const REPLY_BADGE: Record<
  AgentReply["kind"],
  { variant: "success" | "info" | "warning" | "accent" | "danger"; label: (reply: AgentReply) => string }
> = {
  grounded: {
    variant: "success",
    label: (reply) =>
      reply.kind === "grounded"
        ? `Grounded answer · ${reply.citations.length} source${reply.citations.length === 1 ? "" : "s"}`
        : "",
  },
  clarifying: { variant: "info", label: () => "Clarifying question" },
  greeting: { variant: "info", label: () => "Assistant greeting" },
  guard: { variant: "info", label: () => "Guidelines applied" },
  conflict: { variant: "warning", label: () => "Conflicting evidence" },
  unsupported: { variant: "warning", label: () => "No supporting evidence" },
  uncertain: { variant: "warning", label: () => "Couldn't confirm an answer" },
  escalation_offer: { variant: "accent", label: () => "Needs a human" },
  error: { variant: "danger", label: () => "No response" },
};

/** New exchange divider when ≥ 30 minutes passed or the day changed. */
function needsDivider(previous: ChatMessage, current: ChatMessage): boolean {
  const prevIso =
    previous.kind === "system" ? undefined : (previous.createdAt ?? undefined);
  const currIso = current.kind === "system" ? undefined : (current.createdAt ?? undefined);
  if (!prevIso || !currIso) return false;
  const prev = new Date(prevIso).getTime();
  const curr = new Date(currIso).getTime();
  if (Number.isNaN(prev) || Number.isNaN(curr)) return false;
  return curr - prev >= 30 * 60 * 1000;
}

function TimeDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-1" role="presentation">
      <span className="h-px flex-1 bg-line" />
      <span className="text-[10px] font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

function dividerLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (sameDay) return time;
  const day = date.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${day} · ${time}`;
}

export function MessageTimeline({
  messages,
  thinking,
  ticketId,
  documentTitles,
  onFeedback,
  onRetry,
  onEscalate,
  onPick,
  onOpenTicket,
  onInspectEvidence,
  onStop,
  onEditQuery,
}: MessageTimelineProps) {
  // Consecutive assistant messages form one run: the identity row is
  // rendered once; follow-ups align to the same gutter.
  let assistantRunOpen = false;

  // The newest user message can be edited (prefilled into the composer);
  // earlier history stays append-only.
  let lastUserIndex = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].kind === "user") {
      lastUserIndex = i;
      break;
    }
  }

  return (
    <div className="space-y-6">
      {messages.map((message, index) => {
        const previous = index > 0 ? messages[index - 1] : null;
        const showDivider = previous !== null && needsDivider(previous, message);
        const dividerLabelValue =
          previous && message.kind !== "system" && message.createdAt
            ? dividerLabel(message.createdAt)
            : "";

        if (message.kind === "user") {
          assistantRunOpen = false;
          const canEdit = index === lastUserIndex && typeof onEditQuery === "function";
          return (
            <Fragment key={message.id}>
              {showDivider && dividerLabelValue && <TimeDivider label={dividerLabelValue} />}
              <div className="group flex flex-col items-end animate-rise-in">
                <div className="max-w-[80%] rounded-2xl rounded-br-md bg-surface-3 px-4 py-2.5 text-[15px] leading-relaxed text-ink md:max-w-[65%]">
                  {message.text}
                </div>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => onEditQuery?.(message.text)}
                    className={cn(
                      "mt-1 flex items-center gap-1 rounded-control px-1.5 py-0.5 text-[11px] text-ink-muted",
                      "opacity-0 transition-opacity duration-fast group-hover:opacity-100 group-focus-within:opacity-100",
                      "hover:text-ink focus-visible:opacity-100 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                    )}
                  >
                    <Pencil aria-hidden="true" className="size-3" />
                    Edit
                  </button>
                )}
              </div>
            </Fragment>
          );
        }

        if (message.kind === "system") {
          assistantRunOpen = false;
          return (
            <Fragment key={message.id}>
              {showDivider && dividerLabelValue && <TimeDivider label={dividerLabelValue} />}
              <div className="flex justify-center animate-fade-in">
                <button
                  type="button"
                  onClick={message.ticketId ? onOpenTicket : undefined}
                  disabled={!message.ticketId}
                  className="inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-surface-1 px-3.5 py-1.5 text-xs text-ink-secondary transition-colors duration-fast hover:border-line-strong hover:text-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-default"
                >
                  <span className="truncate">{message.text}</span>
                  {message.ticketId && (
                    <span className="shrink-0 font-mono text-[11px] text-accent-ink">
                      view
                    </span>
                  )}
                </button>
              </div>
            </Fragment>
          );
        }

        const { reply } = message;
        const badge = REPLY_BADGE[reply.kind];
        const showIdentity = !assistantRunOpen;
        assistantRunOpen = true;

        // Grounded answers render answer-first, unboxed.
        const isGrounded = reply.kind === "grounded";

        return (
          <Fragment key={message.id}>
            {showDivider && dividerLabelValue && <TimeDivider label={dividerLabelValue} />}
            <div className={cn(isGrounded ? "animate-rise-in" : "animate-rise-in")}>
              {/* Identity row — once per assistant run */}
              {showIdentity && (
                <div className="mb-2.5 flex items-center gap-2.5">
                  <span
                    aria-hidden="true"
                    className="flex size-7 shrink-0 items-center justify-center rounded-[8px] border border-accent-border bg-accent-soft"
                  >
                    <LogoMark className="size-4" />
                  </span>
                  <span className="text-[13px] font-medium text-ink">Vilasat AI</span>
                  <Badge variant={badge.variant} className="shrink-0">
                    {badge.label(reply)}
                  </Badge>
                  <span className="ml-auto shrink-0 text-[11px] text-ink-muted">
                    {message.time}
                  </span>
                </div>
              )}

              <div className={cn(!showIdentity && "ml-0")}>
                {isGrounded && (
                  <GroundedAnswer
                    text={reply.text}
                    citations={reply.citations}
                    onInspect={
                      onInspectEvidence
                        ? () => onInspectEvidence(reply.citations, reply.text)
                        : undefined
                    }
                  />
                )}
                {reply.kind === "clarifying" && (
                  <ClarifyingCard text={reply.text} options={reply.options} onPick={onPick} />
                )}
                {reply.kind === "greeting" && (
                  <ClarifyingCard text={reply.text} options={reply.options} onPick={onPick} />
                )}
                {reply.kind === "guard" && (
                  <GuardCard text={reply.text} options={reply.options} onPick={onPick} />
                )}

                {/* Dead ends + errors: semantic callouts (left rule + soft fill) */}
                {reply.kind === "conflict" && (
                  <div className="rounded-card border-l-[3px] border-l-warning bg-warning-soft/60 p-4">
                    <FallbackCard
                      title="The documentation doesn't give a reliable answer"
                      text={reply.text}
                      checkedDocIds={reply.checkedDocIds}
                      suggestions={reply.suggestions}
                      escalationOffer={reply.escalationOffer}
                      documentTitles={documentTitles}
                      ticketId={ticketId}
                      onEscalate={onEscalate}
                      onPick={onPick}
                    />
                  </div>
                )}
                {reply.kind === "unsupported" && (
                  <div className="rounded-card border-l-[3px] border-l-warning bg-warning-soft/60 p-4">
                    <FallbackCard
                      text={reply.text}
                      checkedDocIds={reply.checkedDocIds}
                      suggestions={reply.suggestions}
                      escalationOffer={reply.escalationOffer}
                      documentTitles={documentTitles}
                      ticketId={ticketId}
                      onEscalate={onEscalate}
                      onPick={onPick}
                    />
                  </div>
                )}
                {reply.kind === "uncertain" && (
                  <div className="rounded-card border-l-[3px] border-l-info bg-info-soft/60 p-4">
                    <FallbackCard
                      title="I found related documentation but couldn't confirm an answer"
                      text={reply.text}
                      checkedDocIds={reply.checkedDocIds}
                      suggestions={reply.suggestions}
                      escalationOffer={reply.escalationOffer}
                      documentTitles={documentTitles}
                      ticketId={ticketId}
                      onEscalate={onEscalate}
                      onPick={onPick}
                    />
                  </div>
                )}
                {reply.kind === "escalation_offer" && (
                  <EscalationOfferCard
                    text={reply.text}
                    ticketId={ticketId}
                    onEscalate={onEscalate}
                  />
                )}
                {reply.kind === "error" && (
                  <div className="rounded-card border-l-[3px] border-l-line-strong bg-surface-1/70 p-4">
                    {message.cancelled ? (
                      <CancelledCard
                        onRetry={() => onRetry(message.id)}
                        onEdit={
                          onEditQuery
                            ? () => onEditQuery(message.failedTurn?.content ?? "")
                            : undefined
                        }
                      />
                    ) : (
                      <ErrorRetryCard
                        text={reply.text}
                        onRetry={
                          message.failedTurn ? () => onRetry(message.id) : undefined
                        }
                      />
                    )}
                  </div>
                )}

                {reply.kind !== "error" && (
                  <div
                    className={cn(
                      "mt-4 border-t border-line pt-3",
                      !showIdentity && "mt-3",
                      isGrounded && "max-w-[65ch]",
                    )}
                  >
                    <FeedbackControl
                      value={message.feedback?.value}
                      reason={message.feedback?.reason}
                      onChange={(value, reason) => onFeedback(message.id, value, reason)}
                    />
                  </div>
                )}
              </div>
            </div>
          </Fragment>
        );
      })}

      {thinking && (
        <div className="animate-fade-in">
          <ThinkingIndicator />
          {onStop && (
            <div className="mt-3 md:ml-11">
              <Button
                variant="ghost"
                size="sm"
                onClick={onStop}
                className="gap-1.5 text-ink-muted hover:text-ink"
                title="Stop waiting for this response (Esc)"
              >
                <Square aria-hidden="true" className="size-3" />
                Stop
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
