/**
 * Staff ticket presentation mapping.
 *
 * The API is the source of truth. This module only formats stored values,
 * merges conversation messages with ticket lifecycle events, and derives
 * the AI outcome that preceded escalation. It never calls the agent,
 * retrieval, or a summarizer.
 */

import type {
  AgentReply,
  ApiCitation,
  ApiStaffReply,
  ApiTicketDetail,
  ApiTicketEvent,
  ApiTicketPriority,
  ApiTicketStatus,
  ApiTicketSummary,
} from "@/lib/api/client";
import { toUiStatus } from "@/lib/api/client";
import { STATUS_LABEL, type TicketStatus } from "@/lib/support/tickets";

const API_STATUSES: ApiTicketStatus[] = ["OPEN", "IN_PROGRESS", "RESOLVED"];

export interface StaffTicketSummary {
  id: string;
  customer: { name: string; email: string; phone: string | null };
  summary: string;
  status: TicketStatus;
  priority: ApiTicketPriority;
  /** Human display form ("Today · 9:41 AM"). */
  createdAt: string;
  /** Raw server timestamp for relative rendering. */
  createdAtIso: string;
  updatedAt: string;
  escalationReason: string;
}

type TimelineBase = {
  id: string;
  createdAt: string;
  time: string;
};

export type StaffTimelineRow =
  | (TimelineBase & { kind: "customer"; text: string })
  | (TimelineBase & {
      kind: "ai";
      reply: AgentReply;
      citations: ApiCitation[];
    })
  | (TimelineBase & {
      kind: "system";
      text: string;
      event?: "escalation" | "status" | "other";
    });

export interface StaffTicketDetail extends StaffTicketSummary {
  originalQuestion: string;
  messages: StaffTimelineRow[];
  messageCount: number;
  eventCount: number;
  /** Last assistant outcome stored before the ticket was created. */
  aiOutcome: AgentReply["kind"] | null;
  /** Staff replies sent from the composer, oldest first (stored server
   *  records with their honest dispatch outcome — never local state). */
  replies: ApiStaffReply[];
}

export const AI_OUTCOME_LABEL: Record<AgentReply["kind"], string> = {
  grounded: "Grounded answer",
  clarifying: "Clarifying question",
  greeting: "Small talk",
  guard: "Guidelines applied",
  conflict: "Conflicting evidence",
  unsupported: "No supporting evidence",
  uncertain: "Couldn't confirm an answer",
  escalation_offer: "Human hand-off offered",
  error: "Provider error",
};

export const AI_OUTCOME_VARIANT: Record<
  AgentReply["kind"],
  "neutral" | "accent" | "info" | "success" | "warning" | "danger"
> = {
  grounded: "success",
  clarifying: "info",
  greeting: "info",
  guard: "info",
  conflict: "warning",
  unsupported: "warning",
  uncertain: "warning",
  escalation_offer: "accent",
  error: "danger",
};

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Render server timestamps; never invent "today" for an invalid value. */
export function formatTicketTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown time";

  const time = date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);

  if (sameDay(date, now)) return `Today · ${time}`;
  if (sameDay(date, yesterday)) return `Yesterday · ${time}`;

  const includeYear = date.getFullYear() !== now.getFullYear();
  const day = date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  });
  return `${day} · ${time}`;
}

function toApiStatusOrNull(value: string | null): ApiTicketStatus | null {
  return value && (API_STATUSES as string[]).includes(value)
    ? (value as ApiTicketStatus)
    : null;
}

function statusText(value: string | null): string {
  const status = toApiStatusOrNull(value);
  return status ? STATUS_LABEL[toUiStatus(status)] : (value ?? "unknown");
}

export function toStaffSummary(ticket: ApiTicketSummary): StaffTicketSummary {
  return {
    id: ticket.id,
    customer: {
      name: ticket.customerName,
      email: ticket.customerEmail,
      phone: ticket.customerPhone,
    },
    summary: ticket.summary,
    status: toUiStatus(ticket.status),
    priority: ticket.priority,
    createdAt: formatTicketTime(ticket.createdAt),
    createdAtIso: ticket.createdAt,
    updatedAt: formatTicketTime(ticket.updatedAt),
    escalationReason: ticket.escalationReason,
  };
}

/** Queue-friendly relative time ("2h ago"); absolute via formatTicketTime. */
export function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatTicketTime(iso);
}

/** Queue search over id, customer, summary, and reason (presentation only). */

function eventToRow(event: ApiTicketEvent): StaffTimelineRow {
  const base = {
    id: `event-${event.id}`,
    createdAt: event.createdAt,
    time: formatTicketTime(event.createdAt),
  };

  if (event.eventType === "ticket_created") {
    return { ...base, kind: "system", text: "Escalated to support", event: "escalation" };
  }

  if (event.eventType === "status_changed") {
    const text = event.oldValue
      ? `Status changed from ${statusText(event.oldValue)} to ${statusText(event.newValue)} · ${event.actor}`
      : `Status changed to ${statusText(event.newValue)} · ${event.actor}`;
    return { ...base, kind: "system", text, event: "status" };
  }

  return {
    ...base,
    kind: "system",
    text: `Ticket event: ${event.eventType.replaceAll("_", " ")}`,
    event: "other",
  };
}

function messageToRow(
  message: ApiTicketDetail["messages"][number],
): StaffTimelineRow {
  const base = {
    id: `message-${message.id}`,
    createdAt: message.createdAt,
    time: formatTicketTime(message.createdAt),
  };

  if (message.role === "user") {
    return { ...base, kind: "customer", text: message.content };
  }

  if (message.role === "assistant") {
    if (!message.reply) {
      return {
        ...base,
        kind: "system",
        text: "An earlier assistant reply could not be displayed.",
      };
    }
    return {
      ...base,
      kind: "ai",
      reply: message.reply,
      citations: message.citations,
    };
  }

  return { ...base, kind: "system", text: message.content };
}

function lastOutcomeBefore(
  detail: ApiTicketDetail,
  boundaryIso: string,
): AgentReply["kind"] | null {
  const boundary = new Date(boundaryIso).getTime();
  const cutoff = Number.isNaN(boundary) ? Infinity : boundary;

  const candidates = detail.messages
    .filter((message) => {
      if (message.role !== "assistant" || !message.reply) return false;
      const created = new Date(message.createdAt).getTime();
      return Number.isNaN(created) || created <= cutoff;
    })
    .sort(
      (a, b) =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );

  return candidates.at(-1)?.reply?.kind ?? null;
}

export function toStaffDetail(ticket: ApiTicketDetail): StaffTicketDetail {
  const rows = [
    ...ticket.messages.map(messageToRow),
    ...ticket.events.map(eventToRow),
  ]
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const aTime = new Date(a.row.createdAt).getTime();
      const bTime = new Date(b.row.createdAt).getTime();
      const aValid = !Number.isNaN(aTime);
      const bValid = !Number.isNaN(bTime);
      if (aValid && bValid && aTime !== bTime) return aTime - bTime;
      return a.index - b.index;
    })
    .map(({ row }) => row);

  const escalationEvent = ticket.events.find(
    (event) => event.eventType === "ticket_created",
  );

  return {
    ...toStaffSummary(ticket),
    originalQuestion: ticket.originalQuestion,
    messages: rows,
    messageCount: ticket.messages.length,
    eventCount: ticket.events.length,
    aiOutcome: lastOutcomeBefore(ticket, escalationEvent?.createdAt ?? ticket.createdAt),
    replies: ticket.replies ?? [],
  };
}
