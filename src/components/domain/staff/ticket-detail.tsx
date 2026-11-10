"use client";

import { AlertTriangle, ArrowLeft, Bot, Check, Copy, Mail, Send, Ticket, UserRound, Phone } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import { StaffTimeline } from "./staff-timeline";
import { cn } from "@/lib/utils";
import {
  AI_OUTCOME_LABEL,
  AI_OUTCOME_VARIANT,
  formatTicketTime,
  type StaffTicketDetail,
} from "@/lib/staff/ticket-view";
import { STATUS_OPTIONS, STATUS_LABEL, type TicketStatus } from "@/lib/support/tickets";

interface TicketDetailProps {
  ticket: StaffTicketDetail | null;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onStatusChange: (id: string, status: TicketStatus, expected: TicketStatus) => void;
  statusPending: boolean;
  staleNotice: string | null;
  onBack: () => void;
  /** One soft pulse right after a status transition. */
  pulse?: boolean;
  /** Send one reply (channel decides delivery): "gmail" opens Gmail
   *  compose pre-filled (the staff member presses Send there), "smtp"
   *  dispatches server-side. The workspace stores the reply, refreshes
   *  the detail, and toasts the outcome. Throws ApiError so the
   *  composer can show the failure inline. */
  onSendReply: (ticketId: string, message: string, channel: "smtp" | "gmail") => Promise<void>;
  /** Signed-in staff name for the reply signature. */
  staffName: string;
}

/** Mono ticket id with click-to-copy (clipboard API; transient check). */
function CopyTicketId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (permissions/insecure context) — the id is
      // fully visible anyway; nothing to report.
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      title="Copy ticket ID"
      aria-label={`Copy ticket ID ${id}`}
      className={cn(
        "group inline-flex items-center gap-1.5 rounded-control px-1 py-0.5 font-mono text-sm font-medium text-ink",
        "transition-colors duration-fast hover:bg-surface-2 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
      )}
    >
      {id}
      {copied ? (
        <Check aria-hidden="true" className="size-3.5 text-success" />
      ) : (
        <Copy
          aria-hidden="true"
          className="size-3.5 text-ink-muted opacity-0 transition-opacity duration-fast group-hover:opacity-100"
        />
      )}
      <span aria-live="polite" className="sr-only">
        {copied ? "Ticket ID copied" : ""}
      </span>
    </button>
  );
}

function DetailSkeleton() {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6 md:px-6" aria-hidden="true">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-5 w-3/4" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-24 w-full rounded-card" />
        <Skeleton className="h-24 w-full rounded-card" />
      </div>
      <Skeleton className="h-20 w-full rounded-card" />
      <Skeleton className="h-32 w-full rounded-card" />
    </div>
  );
}

/**
 * Reply composer — write a message and hand it to Gmail.
 *
 * Clicking "Send via Gmail" opens Gmail's compose window in a new tab
 * with the recipient, subject, and message pre-filled; the staff member
 * presses Send there to actually deliver the email. The reply is still
 * STORED with the ticket (channel "gmail", honestly marked as a
 * hand-off — the app cannot see Gmail's outbox), so the sent history
 * below renders those stored records.
 *
 * Popup-safety: window.open runs synchronously inside the click handler
 * (user gesture intact). If the store call then fails, the opened tab
 * is closed again and the error is shown inline.
 */
function ReplyComposer({
  ticket,
  staffName,
  onSendReply,
}: {
  ticket: StaffTicketDetail;
  staffName: string;
  onSendReply: (ticketId: string, message: string, channel: "smtp" | "gmail") => Promise<void>;
}) {
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function gmailComposeUrl(): string {
    const subject = `[${ticket.id}] ${ticket.summary}`;
    const bodyWithSignature =
      body.trim() + `\n\n— ${staffName}\nNorthstar Desk Support`;
    const params = new URLSearchParams({
      view: "cm",
      fs: "1",
      to: ticket.customer.email,
      su: subject,
      body: bodyWithSignature,
    });
    return `https://mail.google.com/mail/?${params.toString()}`;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = body.trim();
    if (sending) return;
    if (!message) {
      setError("Write a message before sending.");
      return;
    }

    // Open synchronously inside the gesture — a window.open after an
    // await is treated as a popup and blocked by browsers.
    const gmailTab = window.open(gmailComposeUrl(), "_blank", "noopener,noreferrer");

    setSending(true);
    setError(null);
    try {
      await onSendReply(ticket.id, message, "gmail");
      setBody("");
    } catch (sendError) {
      // The reply was NOT stored — don't leave a dangling Gmail tab.
      if (gmailTab && !gmailTab.closed) gmailTab.close();
      setError(
        sendError instanceof Error && sendError.message
          ? sendError.message
          : "The reply could not be sent. Nothing was lost — try again."
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(event)}
      className="mt-8 rounded-card border border-line bg-surface-1 p-4"
      noValidate
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          Reply to customer
        </p>
        <span className="flex items-center gap-1.5 text-xs text-ink-secondary">
          <Mail aria-hidden="true" className="size-3.5 text-ink-muted" />
          {ticket.customer.email}
        </span>
      </div>

      <Textarea
        value={body}
        onChange={(event) => {
          setBody(event.target.value);
          if (error) setError(null);
        }}
        placeholder="Write the message the customer will receive by email…"
        aria-label="Reply message"
        maxLength={4000}
        rows={4}
        className="mt-3"
      />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p aria-live="polite" className="text-xs text-danger-ink">
          {error ?? ""}
        </p>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {body.length}/4000
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] leading-relaxed text-ink-muted">
          Opens Gmail compose in a new tab with this message pre-filled —
          press Send there to deliver it.
        </p>
        <Button type="submit" size="sm" loading={sending} disabled={!body.trim()}>
          <Send aria-hidden="true" />
          Send via Gmail
        </Button>
      </div>
    </form>
  );
}

/** Stored record of every reply sent from this workspace. */
function SentReplies({ ticket }: { ticket: StaffTicketDetail }) {
  if (ticket.replies.length === 0) return null;

  return (
    <section aria-label="Sent replies" className="mt-6">
      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
        Sent replies ({ticket.replies.length})
      </h3>
      <ul className="space-y-3">
        {ticket.replies.map((reply) => (
          <li key={reply.id} className="rounded-card border border-line bg-canvas p-4">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-sm font-medium text-ink">{reply.staffName}</span>
              <span aria-hidden="true" className="text-ink-muted">·</span>
              <span className="text-xs tabular-nums text-ink-muted">
                {formatTicketTime(reply.createdAt)}
              </span>
              <span className="ml-auto">
                {reply.dispatchChannel === "gmail" ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-info-border bg-info-soft px-2 py-0.5 text-[10px] font-medium text-info-ink">
                    <Send aria-hidden="true" className="size-3" />
                    Sent via Gmail
                  </span>
                ) : reply.emailDispatched ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-success-border bg-success-soft px-2 py-0.5 text-[10px] font-medium text-success-ink">
                    <Check aria-hidden="true" className="size-3" />
                    Emailed to {reply.sentTo}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-warning-border bg-warning-soft px-2 py-0.5 text-[10px] font-medium text-warning-ink">
                    <AlertTriangle aria-hidden="true" className="size-3" />
                    Stored — not delivered
                  </span>
                )}
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">
              {reply.body}
            </p>
            {!reply.emailDispatched && reply.dispatchNote && (
              <p className="mt-2 text-[11px] leading-relaxed text-warning-ink">
                {reply.dispatchNote}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Ticket detail: answers "what did the customer ask, what did the AI
 * already try, why was this escalated" from stored server data only.
 * Status changes are sent to the API and applied from its response; the
 * UI never assumes a local transition succeeded.
 */
export function TicketDetail({
  ticket,
  loading,
  error,
  onRetry,
  onStatusChange,
  statusPending,
  staleNotice,
  onBack,
  pulse = false,
  onSendReply,
  staffName,
}: TicketDetailProps) {
  if (!ticket && loading) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="shrink-0 border-b border-line px-4 py-4 md:px-6">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="mt-3 h-6 w-2/3" />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <DetailSkeleton />
        </div>
      </div>
    );
  }

  if (!ticket && error) {
    return (
      <div className="flex h-full items-center justify-center">
        <ErrorState
          title="Couldn't load this ticket"
          description="The ticket service didn't respond. Nothing was changed — try again."
          onRetry={onRetry}
        />
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <EmptyState
          icon={<Ticket className="size-5" />}
          title="Select a ticket"
          description="Choose an escalation from the queue to see the customer, the conversation, and why it was escalated."
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Detail header */}
      <header className="shrink-0 border-b border-line bg-canvas/85 px-4 py-4 backdrop-blur-md md:px-6">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="lg:hidden">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <ArrowLeft aria-hidden="true" />
              Queue
            </Button>
          </span>
          <CopyTicketId id={ticket.id} />
          <StatusBadge status={ticket.status} pulse={pulse} />
          {ticket.priority === "high" && (
            <Badge variant="accent" className="uppercase">
              High priority
            </Badge>
          )}
          <span className="ml-auto text-[11px] text-ink-muted">
            Created {ticket.createdAt}
          </span>
        </div>

        <p className="mt-2 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          Customer-provided issue summary
        </p>
        <h2 className="mt-0.5 font-display text-lg font-semibold tracking-tight text-ink">
          {ticket.summary}
        </h2>

        {/* Status management */}
        <div
          role="group"
          aria-label="Change ticket status"
          aria-busy={statusPending}
          className="mt-3 flex flex-wrap items-center gap-2"
        >
          <span className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
            Status
          </span>
          {STATUS_OPTIONS.map((option) => {
            const active = ticket.status === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                disabled={statusPending}
                onClick={() => onStatusChange(ticket.id, option.value, ticket.status)}
                className={cn(
                  "rounded-control border px-3 py-1.5 text-[13px] font-medium transition-colors duration-fast",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-default",
                  active
                    ? "border-accent-border bg-accent-soft text-accent-ink"
                    : "border-line bg-surface-1 text-ink-secondary hover:border-line-strong hover:text-ink disabled:opacity-60"
                )}
              >
                {STATUS_LABEL[option.value]}
              </button>
            );
          })}
          {statusPending && (
            <span role="status" className="text-[11px] text-ink-muted">
              Updating status…
            </span>
          )}
        </div>

        {staleNotice && (
          <p
            role="alert"
            className="mt-3 rounded-control border border-warning-border bg-warning-soft p-2.5 text-xs leading-relaxed text-warning-ink"
          >
            {staleNotice}
          </p>
        )}
      </header>

      {/* Detail body */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
          {/* At-a-glance: the three questions staff need answered */}
          <section aria-label="Escalation context" className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-card border border-line bg-surface-1 p-4">
                <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                  <UserRound aria-hidden="true" className="size-3.5" />
                  Customer
                </p>
                <p className="mt-2 text-sm font-medium text-ink">{ticket.customer.name}</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-secondary">
                  <Mail aria-hidden="true" className="size-3.5 text-ink-muted" />
                  {ticket.customer.email}
                </p>
                {ticket.customer.phone && (
                  <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-secondary">
                    <Phone aria-hidden="true" className="size-3.5 text-ink-muted" />
                    {ticket.customer.phone}
                  </p>
                )}
              </div>

              <div className="rounded-card border border-warning-border bg-warning-soft p-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-warning-ink">
                  Escalation reason (customer request)
                </p>
                <p className="mt-2 text-sm leading-relaxed text-ink">
                  {ticket.escalationReason}
                </p>
              </div>

              {/* Deterministic escalation context — no generated summary */}
              <div className="rounded-card border border-info-border bg-info-soft p-4">
                <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-info-ink">
                  <Bot aria-hidden="true" className="size-3.5" />
                  AI outcome at escalation
                </p>
                {ticket.aiOutcome ? (
                  <div className="mt-2">
                    <Badge variant={AI_OUTCOME_VARIANT[ticket.aiOutcome]}>
                      {AI_OUTCOME_LABEL[ticket.aiOutcome]}
                    </Badge>
                  </div>
                ) : (
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                    No assistant reply was stored before this ticket was created.
                  </p>
                )}
                <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
                  Derived from the last stored assistant reply. Not a generated summary — opening
                  this ticket never runs the agent.
                </p>
              </div>
            </div>

            {/* Original question */}
            <div className="rounded-card border border-line bg-surface-1 p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                Original question
              </p>
              <p className="mt-2 text-[15px] leading-relaxed text-ink">
                {ticket.originalQuestion}
              </p>
            </div>
          </section>

          {/* Conversation */}
          <section aria-labelledby="transcript-heading" className="mt-8">
            <div className="mb-4 flex items-center justify-between gap-3 border-t border-line pt-6">
              <h3
                id="transcript-heading"
                className="text-[11px] font-medium uppercase tracking-wide text-ink-muted"
              >
                Conversation
              </h3>
              <span className="text-[11px] tabular-nums text-ink-muted">
                {ticket.messageCount} message{ticket.messageCount === 1 ? "" : "s"} ·{" "}
                {ticket.eventCount} event{ticket.eventCount === 1 ? "" : "s"}
              </span>
            </div>
            <StaffTimeline rows={ticket.messages} customerName={ticket.customer.name} />
          </section>

          {/* Reply to the customer straight from this view */}
          <ReplyComposer ticket={ticket} staffName={staffName} onSendReply={onSendReply} />
          <SentReplies ticket={ticket} />
        </div>
      </div>
    </div>
  );
}
