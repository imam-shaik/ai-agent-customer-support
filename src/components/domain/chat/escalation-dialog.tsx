"use client";

import { useEffect, useId, useState } from "react";
import { CheckCircle, Info, MessageSquareText, Ticket } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  api,
  ApiError,
  type ApiActiveTicket,
  type ApiTicketDetail,
  type ApiTicketStatus,
} from "@/lib/api/client";

export interface ContactInfo {
  name: string;
  email: string;
  /** Optional second contact channel; may be left blank. */
  phone: string;
}

export interface TicketRecord {
  id: string;
  summary: string;
  contact: ContactInfo;
  originalQuestion: string;
  contextMessages: number;
  createdAt: string;
  status: ApiTicketStatus;
}

const PURPOSE =
  "For follow-up if your issue needs to be escalated to our support team.";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_SUMMARY = 300;
/** Optional phone: digits with optional +, spaces, dashes, parentheses. */
const PHONE_PATTERN = /^\+?[0-9][0-9()\-\s]{6,31}$/;

const STATUS_LABEL: Record<ApiTicketStatus, string> = {
  OPEN: "Open — queued for review",
  IN_PROGRESS: "In progress — a support agent is reviewing it",
  RESOLVED: "Resolved",
};

const STATUS_CHIP: Record<ApiTicketStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  RESOLVED: "Resolved",
};

type EscalationErrors = Partial<Record<"name" | "email" | "phone" | "summary", string>>;

function validate(contact: ContactInfo, summary: string): EscalationErrors {
  const errors: EscalationErrors = {};
  if (contact.name.trim().length < 2) {
    errors.name = "Enter your name so the team knows who to reply to.";
  }
  if (!contact.email.trim()) {
    errors.email = "Enter an email so the team can reach you.";
  } else if (!EMAIL_PATTERN.test(contact.email.trim())) {
    errors.email = "That doesn't look like a valid email address.";
  }
  // Phone is OPTIONAL — validated only when the customer chose to add one.
  if (contact.phone.trim() && !PHONE_PATTERN.test(contact.phone.trim())) {
    errors.phone = "That doesn't look like a phone number — leave it blank or use digits.";
  }
  if (summary.trim().length < 3) {
    errors.summary = "Add a short summary so the agent has the short version.";
  } else if (summary.trim().length > MAX_SUMMARY) {
    errors.summary = `Keep the summary to ${MAX_SUMMARY} characters or fewer.`;
  }
  return errors;
}

export function formatTicketTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function ticketRecordFromDetail(detail: ApiTicketDetail): TicketRecord {
  return {
    id: detail.id,
    summary: detail.summary,
    contact: { name: detail.customerName, email: detail.customerEmail, phone: detail.customerPhone ?? "" },
    originalQuestion: detail.originalQuestion,
    contextMessages: detail.messages.length,
    createdAt: formatTicketTime(detail.createdAt),
    status: detail.status,
  };
}

export function ticketRecordFromActive(active: ApiActiveTicket): TicketRecord {
  return {
    id: active.id,
    summary: active.summary,
    contact: { name: active.customerName, email: active.customerEmail, phone: active.customerPhone ?? "" },
    originalQuestion: active.originalQuestion,
    contextMessages: active.messageCount,
    createdAt: formatTicketTime(active.createdAt),
    status: active.status,
  };
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
      <span className="w-32 shrink-0 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </span>
      <span className="min-w-0 break-words text-sm text-ink-secondary">{value}</span>
    </div>
  );
}

interface EscalationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Conversation the ticket is attached to (real backend id). */
  conversationId: string | null;
  /** The message that triggered escalation. */
  originalQuestion: string;
  /** Number of messages that will be attached as context. */
  contextMessages: number;
  /** Deterministic reason derived from the reply kind (never model text). */
  escalationReason?: string;
  contact: ContactInfo;
  onContactChange: (contact: ContactInfo) => void;
  /** Existing ticket, if one was already created in this session. */
  ticket: TicketRecord | null;
  onCreated: (ticket: TicketRecord) => void;
}

/**
 * Escalation flow: details → review & submit → ticket success.
 * Submits through the real Phase 5 endpoint; no ticket id is fabricated.
 */
export function EscalationDialog({
  open,
  onOpenChange,
  conversationId,
  originalQuestion,
  contextMessages,
  escalationReason = "Escalated from customer conversation",
  contact,
  onContactChange,
  ticket,
  onCreated,
}: EscalationDialogProps) {
  const [summary, setSummary] = useState(originalQuestion);
  const [errors, setErrors] = useState<EscalationErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const summaryId = useId();

  // A ticket already exists → reopen straight to the success step.
  const step: "details" | "success" = ticket ? "success" : "details";

  useEffect(() => {
    if (open) {
      setSummary((current) =>
        current.trim() ? current.slice(0, MAX_SUMMARY) : originalQuestion.slice(0, MAX_SUMMARY)
      );
      setErrors({});
      setSubmitting(false);
      setSubmitError(null);
    }
  }, [open, originalQuestion]);

  // Submit stays enabled so validation feedback can always appear on attempt.
  const canSubmit = !submitting;

  function clearError(field: keyof EscalationErrors) {
    setErrors((current) => (current[field] ? { ...current, [field]: undefined } : current));
  }

  function updateContact(next: ContactInfo) {
    onContactChange(next);
    clearError("name");
    clearError("email");
    clearError("phone");
  }

  async function handleSubmit() {
    const nextErrors = validate(contact, summary);
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) return;

    if (!conversationId) {
      setSubmitError("Start a conversation before contacting the support team.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const detail = await api.tickets.createEscalation(conversationId, {
        customerName: contact.name.trim(),
        customerEmail: contact.email.trim(),
        customerPhone: contact.phone.trim() || undefined,
        summary: summary.trim(),
        originalQuestion: originalQuestion.slice(0, 4000) || summary.trim(),
        escalationReason,
      });
      onCreated(ticketRecordFromDetail(detail));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const details = error.details as { ticketId?: string } | undefined;
        if (details?.ticketId) {
          try {
            const existing = await api.tickets.get(details.ticketId);
            onCreated(ticketRecordFromDetail(existing));
            return;
          } catch {
            setSubmitError("This conversation already has an open ticket.");
            return;
          }
        }
        setSubmitError("This conversation already has an open ticket.");
        return;
      }
      setSubmitError(
        "We couldn't create the ticket. Nothing was lost — please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "success" && ticket) {
    return (
      <Modal
        open={open}
        onOpenChange={onOpenChange}
        title="Ticket created"
        description="Your conversation has been handed to the Northstar Desk support team."
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Back to conversation
            </Button>
          </>
        }
      >
        <div className="animate-fade-in">
          <div className="flex items-center gap-3 rounded-control border border-success-border bg-success-soft p-4">
            <CheckCircle aria-hidden="true" className="size-5 shrink-0 text-success-ink" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-success-ink">
                We’ve received your request
              </p>
              <p className="mt-0.5 font-mono text-lg font-semibold tracking-tight text-ink">
                {ticket.id}
              </p>
            </div>
          </div>

          <dl className="mt-5 space-y-3">
            <ReviewRow label="Issue" value={ticket.summary} />
            <ReviewRow
              label="Contact"
              value={
                ticket.contact.name || ticket.contact.email
                  ? `${ticket.contact.name}${ticket.contact.name && ticket.contact.email ? " · " : ""}${ticket.contact.email}`
                  : "—"
              }
            />
            <ReviewRow
              label="Attached"
              value={`${ticket.contextMessages} message${ticket.contextMessages === 1 ? "" : "s"} from this conversation`}
            />
            <ReviewRow label="Created" value={ticket.createdAt} />
            <ReviewRow label="Status" value={STATUS_LABEL[ticket.status]} />
          </dl>

          <div className="mt-5 rounded-control border border-line bg-surface-2 p-4">
            <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              What happens next
            </p>
            <ol className="mt-2.5 space-y-2 text-sm leading-relaxed text-ink-secondary">
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-accent-ink">1</span>
                A support agent reviews your conversation and the attached context.
              </li>
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-accent-ink">2</span>
                We reply by email to {ticket.contact.email || "your contact address"}, usually
                within one business day.
              </li>
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-accent-ink">3</span>
                You can keep asking questions here in the meantime — reference the ticket ID.
              </li>
            </ol>
          </div>

          <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-ink-muted">
            <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            Your conversation and its citations are attached to this request.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Contact the support team"
      description="Review the details below before your request is sent to a human agent."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting} disabled={!canSubmit}>
            {!submitting && <Ticket aria-hidden="true" />}
            {submitting ? "Creating ticket…" : "Submit request"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {/* Contact collection */}
        <section aria-labelledby="esc-contact" className="animate-fade-in">
          <h3 id="esc-contact" className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
            Your details
          </h3>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Field label="Name" required error={errors.name} hint="How should the agent address you?">
              <Input
                value={contact.name}
                autoComplete="name"
                placeholder="Alex Rivera"
                onChange={(event) => updateContact({ ...contact, name: event.target.value })}
              />
            </Field>
            <Field
              label="Contact email"
              required
              error={errors.email}
              hint="Used only for this request."
            >
              <Input
                type="email"
                value={contact.email}
                autoComplete="email"
                placeholder="alex@company.com"
                onChange={(event) => updateContact({ ...contact, email: event.target.value })}
              />
            </Field>
            <Field
              label="Phone (optional)"
              error={errors.phone}
              hint="Only if you'd like a call back."
            >
              <Input
                type="tel"
                value={contact.phone}
                autoComplete="tel"
                placeholder="+1 555 010 2030"
                onChange={(event) => updateContact({ ...contact, phone: event.target.value })}
              />
            </Field>
          </div>
          <p className="mt-3 flex items-start gap-2 rounded-control border border-info-border bg-info-soft p-3 text-xs leading-relaxed text-info-ink">
            <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            {PURPOSE}
          </p>
        </section>

        {/* Review */}
        <section aria-labelledby="esc-review" className="border-t border-line pt-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 id="esc-review" className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              Review before submitting
            </h3>
            <Badge variant="accent">
              <MessageSquareText aria-hidden="true" className="size-3" />
              {contextMessages} message{contextMessages === 1 ? "" : "s"} attached
            </Badge>
          </div>

          <div className="mt-3 space-y-3 rounded-control border border-line bg-surface-2 p-4">
            <ReviewRow
              label="Original question"
              value={originalQuestion.length > 220 ? `${originalQuestion.slice(0, 220)}…` : originalQuestion}
            />
          </div>

          <div className="mt-4">
            <Field
              id={summaryId}
              label="Issue summary"
              error={errors.summary}
              hint={`Edit this so the agent gets the short version. ${MAX_SUMMARY} characters max.`}
            >
              <Textarea
                id={summaryId}
                rows={3}
                value={summary}
                maxLength={MAX_SUMMARY}
                onChange={(event) => {
                  setSummary(event.target.value);
                  clearError("summary");
                  setSubmitError(null);
                }}
                placeholder="One or two sentences describing the issue"
              />
            </Field>
          </div>

          {submitError && (
            <p role="alert" className="mt-3 rounded-control border border-danger-border bg-danger-soft p-3 text-xs leading-relaxed text-danger-ink">
              {submitError}
            </p>
          )}
        </section>
      </div>
    </Modal>
  );
}

/** Compact header chip that reopens the ticket view — visually secondary
 *  to the conversation: neutral surface, mono id, quiet status dot. */
export function TicketChip({
  ticket,
  onClick,
  className,
}: {
  ticket: TicketRecord;
  onClick: () => void;
  className?: string;
}) {
  const dot =
    ticket.status === "RESOLVED"
      ? "bg-success"
      : ticket.status === "IN_PROGRESS"
        ? "bg-info"
        : "bg-warning";
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${ticket.id} · ${STATUS_CHIP[ticket.status]} — view ticket`}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface-1 px-2.5 py-1",
        "text-[11px] text-ink-secondary transition-colors duration-fast hover:border-line-strong hover:text-ink",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
        className
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", dot)} />
      <span className="shrink-0 font-mono">{ticket.id}</span>
      <span aria-hidden="true" className="hidden shrink-0 text-ink-muted sm:inline">
        ↗
      </span>
    </button>
  );
}
