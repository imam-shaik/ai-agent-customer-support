"use client";

import type { ReactNode } from "react";
import { FileText, Info, Loader2, ShieldCheck, Ticket } from "lucide-react";
import type { AgentReply } from "@/lib/api/client";
import { SourceCard } from "./source-card";
import type { ChatMessage } from "./message-timeline";
import { cn } from "@/lib/utils";

export interface MyTicketRow {
  id: string;
  status: string;
  summary: string;
  /** ISO timestamp from the server. */
  createdAt: string;
}

const TICKET_STATUS_BADGE: Record<string, { variant: "success" | "info" | "warning"; label: string }> = {
  OPEN: { variant: "warning", label: "Open" },
  IN_PROGRESS: { variant: "info", label: "In progress" },
  RESOLVED: { variant: "success", label: "Resolved" },
};

function formatTicketTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface SourcesRailProps {
  /** Full transcript — the rail derives the LATEST turn from it. */
  messages: ChatMessage[];
  /** True while the real request is in flight. */
  thinking: boolean;
  /** docId -> title, loaded once from the documents endpoint. */
  documentTitles: Record<string, string>;
  /** Number of approved documents in the workspace (null = unknown). */
  documentCount: number | null;
  /** Opens the evidence sheet with one grounded answer's stored citations. */
  onInspectEvidence?: (citations: import("@/lib/api/client").ApiCitation[], context: string) => void;
  /** Every ticket raised from THIS conversation, newest first (server data). */
  myTickets?: MyTicketRow[];
  /** Opens the escalation dialog on one ticket's record. */
  onOpenTicket?: (ticket: MyTicketRow) => void;
  /** False inside containers that already render their own title. */
  showHeader?: boolean;
  className?: string;
}

interface LatestTurn {
  reply: AgentReply;
  citations: import("@/lib/api/client").ApiCitation[];
  /** The user message that produced this reply (when present). */
  question: string | null;
}

function latestTurn(messages: ChatMessage[]): LatestTurn | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.kind === "agent") {
      const question = messages
        .slice(0, index)
        .reverse()
        .find((m) => m.kind === "user");
      return {
        reply: message.reply,
        citations:
          message.reply.kind === "grounded" ? message.reply.citations : [],
        question: question && question.kind === "user" ? question.text : null,
      };
    }
  }
  return null;
}

function checkedDocuments(
  reply: AgentReply,
  documentTitles: Record<string, string>
): Array<{ docId: string; title: string }> {
  const ids =
    reply.kind === "unsupported" ||
    reply.kind === "uncertain" ||
    reply.kind === "conflict"
      ? reply.checkedDocIds
      : [];
  return ids.map((docId) => ({
    docId,
    // Degrade honestly to the raw id when no title is loaded; nothing invented.
    title: documentTitles[docId]?.trim() || docId,
  }));
}

/**
 * Sources rail — what the assistant actually searched for the LATEST turn,
 * rendered strictly from real reply data. Honesty rules:
 *
 * - grounded answers list their stored citations (click -> evidence sheet);
 * - unsupported/uncertain/conflict list the documents that were checked
 *   (checkedDocIds), titled from the workspace's own document list;
 * - clarifying and guard replies say plainly that NO documents were
 *   searched — assessment and the safety screen run before retrieval;
 * - while a request is in flight the rail shows a searching indicator
 *   WITHOUT naming documents: the browser cannot know them until the
 *   response arrives, and inventing them mid-flight would be fabrication.
 */
export function SourcesRail({
  messages,
  thinking,
  documentTitles,
  documentCount,
  onInspectEvidence,
  myTickets,
  onOpenTicket,
  showHeader = true,
  className,
}: SourcesRailProps) {
  const turn = latestTurn(messages);
  const reply = turn?.reply ?? null;

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      {/* ---------- Header ---------- */}
      {showHeader && (
        <div className="shrink-0 border-b border-line px-4 py-3">
          <p className="font-display text-[13px] font-semibold tracking-tight text-ink">
            Sources
          </p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-ink-muted">
            {thinking
              ? "For the message being answered"
              : turn
                ? "For your latest question"
                : "Approved documentation workspace"}
          </p>
        </div>
      )}

      {/* ---------- Body ---------- */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {thinking && (
          <div
            role="status"
            className="flex items-start gap-2.5 rounded-control border border-info-border bg-info-soft p-3 text-xs leading-relaxed text-info-ink"
          >
            <Loader2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 animate-spin" />
            <span>
              Searching the approved documentation
              {turn?.question ? (
                <>
                  {" "}
                  for <span className="font-medium">&ldquo;{turn.question}&rdquo;</span>
                </>
              ) : null}
              &hellip; The matching documents appear here with the answer.
            </span>
          </div>
        )}

        {!thinking && !turn && (
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 rounded-control border border-line bg-surface-2 p-3 text-xs leading-relaxed text-ink-secondary">
              <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-ink-muted" />
              <span>
                Ask a question and the documents used to answer it appear here —
                with the exact supporting passages.
              </span>
            </div>
            {documentCount !== null && (
              <p className="px-1 text-[11px] text-ink-muted">
                {documentCount} approved document{documentCount === 1 ? "" : "s"} in
                this workspace
              </p>
            )}
          </div>
        )}

        {!thinking && turn && reply && reply.kind === "grounded" && (
          <div className="space-y-2.5">
            <p className="px-1 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              Cited for this answer
            </p>
            {turn.citations.map((citation, index) => (
              <button
                key={`${citation.docId}-${citation.sectionId}-${index}`}
                type="button"
                className="w-full rounded-control border border-line/70 bg-surface-1 p-2.5 text-left transition-colors duration-fast hover:border-accent-border hover:bg-surface-2 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
                onClick={() =>
                  onInspectEvidence?.(
                    turn.citations,
                    turn.question ?? "Support question"
                  )
                }
              >
                <SourceCard citation={citation} size="rail" />
              </button>
            ))}
          </div>
        )}

        {!thinking && turn && reply && reply.kind !== "grounded" && reply.kind !== "clarifying" && reply.kind !== "greeting" && reply.kind !== "guard" && (
          <CheckedDocumentsBlock reply={reply} documentTitles={documentTitles} />
        )}

        {!thinking && turn && reply && reply.kind === "clarifying" && (
          <HonestEmpty
            icon={<Info aria-hidden="true" className="size-4 text-info-ink" />}
            title="No documents searched yet"
            body="This turn asked you a clarifying question first. Once you answer, the documentation search runs and its sources appear here."
          />
        )}

        {!thinking && turn && reply && reply.kind === "greeting" && (
          <HonestEmpty
            icon={<Info aria-hidden="true" className="size-4 text-info-ink" />}
            title="No documents searched"
            body="This was a friendly greeting — no documentation search was needed. Ask a support question and the sources appear here."
          />
        )}

        {!thinking && turn && reply && reply.kind === "guard" && (
          <HonestEmpty
            icon={<ShieldCheck aria-hidden="true" className="size-4 text-info-ink" />}
            title="No documents searched"
            body="This message was handled by the safety guidelines before any search, so no documents were involved."
          />
        )}

        {/* ---------- My tickets (this conversation, server data) ---------- */}
        {myTickets && (
          <div className="border-t border-line pt-3">
            <p className="px-1 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              My tickets {myTickets.length > 0 && `(${myTickets.length})`}
            </p>
            {myTickets.length > 0 ? (
              <ul className="mt-2 space-y-1.5">
                {myTickets.map((ticket) => {
                  const badge = TICKET_STATUS_BADGE[ticket.status] ?? {
                    variant: "info" as const,
                    label: ticket.status,
                  };
                  return (
                    <li key={ticket.id}>
                      <button
                        type="button"
                        className="w-full py-2.5 text-left transition-colors duration-fast hover:text-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/40"
                        onClick={() => onOpenTicket?.(ticket)}
                        title={`Open ${ticket.id} (${badge.label})`}
                      >
                        <div className="flex min-w-0 items-center justify-between gap-2">
                          <span className="flex min-w-0 items-center gap-1.5 font-mono text-[11px] font-medium text-ink">
                            <Ticket aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
                            <span className="truncate">{ticket.id}</span>
                          </span>
                          <span className="flex shrink-0 items-center gap-1.5 text-[10px] text-ink-muted">
                            {formatTicketTime(ticket.createdAt)}
                            <span
                              aria-hidden="true"
                              className={cn(
                                "size-1.5 rounded-full",
                                ticket.status === "RESOLVED"
                                  ? "bg-success"
                                  : ticket.status === "IN_PROGRESS"
                                    ? "bg-info"
                                    : "bg-warning"
                              )}
                            />
                          </span>
                        </div>
                        <p className="mt-0.5 truncate text-[12px] text-ink-secondary">
                          {ticket.summary}
                        </p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-2 px-1 text-[11px] leading-relaxed text-ink-muted">
                No tickets raised in this conversation yet. Use
                &ldquo;Contact Support Team&rdquo; under an answer if a human is needed.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CheckedDocumentsBlock({
  reply,
  documentTitles,
}: {
  reply: AgentReply;
  documentTitles: Record<string, string>;
}) {
  const docs = checkedDocuments(reply, documentTitles);
  return (
    <div className="space-y-2.5">
      <p className="px-1 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
        {docs.length > 0
          ? `Documents checked (${docs.length})`
          : "Documents checked"}
      </p>
      {docs.length > 0 ? (
        <>
          <ul className="divide-y divide-line">
            {docs.map((doc) => (
              <li
                key={doc.docId}
                className="flex min-w-0 items-center gap-2.5 py-2"
                title={doc.docId}
              >
                <FileText
                  aria-hidden="true"
                  className="size-3.5 shrink-0 text-ink-muted"
                />
                <span className="min-w-0 truncate text-[13px] leading-snug text-ink-secondary">
                  {doc.title}
                </span>
              </li>
            ))}
          </ul>
          <p className="px-1 text-[11px] leading-relaxed text-ink-muted">
            These were searched, but none could confirm a reliable answer —
            so nothing was invented.
          </p>
        </>
      ) : (
        <HonestEmpty
          icon={<Info aria-hidden="true" className="size-4 text-ink-muted" />}
          title="No documents were searched"
          body="The request was stopped before the documentation search, so no sources are attached to this turn."
        />
      )}
    </div>
  );
}

function HonestEmpty({
  icon,
  title,
  body,
}: {
  icon: ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-control border border-line bg-surface-2 p-3.5">
      <div className="flex items-start gap-2.5">
        {icon}
        <div className="min-w-0">
          <p className="text-[13px] font-medium leading-snug text-ink">{title}</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-secondary">{body}</p>
        </div>
      </div>
    </div>
  );
}
