"use client";

import { useState } from "react";
import { ChevronDown, Ticket, TriangleAlert } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { GroundedAnswer } from "@/components/domain/chat/grounded-answer";
import { REPLY_BADGE } from "@/components/domain/chat/message-timeline";
import type { ApiCitation, AgentReply } from "@/lib/api/client";
import type { StaffTimelineRow } from "@/lib/staff/ticket-view";

/**
 * Staff-side conversation timeline: customer, assistant, and lifecycle
 * events in one readable story. The three voices are visually distinct
 * — customer (quiet bubble), assistant (card, identical to what the
 * customer saw), system (inline hairline rows). Long transcripts
 * collapse to the most recent turns with an "earlier context" expander.
 */

const VISIBLE_WHEN_COLLAPSED = 6;

function RoleLabel({ children, time }: { children: React.ReactNode; time: string }) {
  return (
    <div className="mb-1.5 flex items-center gap-2">
      <span className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">
        {children}
      </span>
      <span className="text-[11px] text-ink-muted">{time}</span>
    </div>
  );
}

function AiReplyBody({
  reply,
  citations,
}: {
  reply: AgentReply;
  citations: ApiCitation[];
}) {
  if (reply.kind === "grounded") {
    return <GroundedAnswer text={reply.text} citations={citations} />;
  }

  if (
    reply.kind === "clarifying" ||
    reply.kind === "guard" ||
    reply.kind === "greeting"
  ) {
    return (
      <div>
        <p className="text-[15px] leading-relaxed text-ink-secondary">{reply.text}</p>
        <p className="mt-3 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          {reply.kind === "guard"
            ? "Then offered to continue with"
            : reply.kind === "greeting"
              ? "Greeted the customer and offered help with"
              : "Asked the customer"}
        </p>
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {reply.options.map((option) => (
            <li
              key={option}
              className="rounded-control border border-line bg-surface-2 px-2.5 py-1 text-[13px] text-ink-secondary"
            >
              {option}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (
    reply.kind === "unsupported" ||
    reply.kind === "uncertain" ||
    reply.kind === "conflict"
  ) {
    return (
      <div>
        <p className="text-[15px] leading-relaxed text-ink-secondary">{reply.text}</p>
        <p className="mt-3 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          {reply.kind === "conflict"
            ? "Document IDs checked — evidence inconsistent"
            : reply.kind === "uncertain"
              ? "Document IDs checked — evidence insufficient"
              : "Document IDs checked — no support found"}
        </p>
        {reply.checkedDocIds.length > 0 && (
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {reply.checkedDocIds.map((docId) => (
              <li
                key={docId}
                title={docId}
                className="max-w-full truncate rounded-full border border-line bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-ink-muted"
              >
                {docId}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (reply.kind === "escalation_offer") {
    return (
      <div>
        <p className="text-[15px] leading-relaxed text-ink-secondary">{reply.text}</p>
        <p className="mt-3 text-[11px] text-ink-muted">
          Escalation was offered to the customer — the customer accepted.
        </p>
      </div>
    );
  }

  return (
    <p role="alert" className="flex gap-2.5 text-[15px] leading-relaxed text-ink-secondary">
      <TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-danger-ink" />
      {reply.text}
    </p>
  );
}

interface StaffTimelineProps {
  rows: StaffTimelineRow[];
  customerName: string;
  className?: string;
}

export function StaffTimeline({ rows, customerName, className }: StaffTimelineProps) {
  const [expanded, setExpanded] = useState(false);
  const collapsedCount = rows.length - VISIBLE_WHEN_COLLAPSED;
  const visible = expanded || rows.length <= VISIBLE_WHEN_COLLAPSED
    ? rows
    : rows.slice(collapsedCount);

  return (
    <div className={className}>
      {!expanded && collapsedCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className={cn(
            "mb-4 flex w-full items-center gap-3 rounded-control border border-line bg-surface-1 px-3.5 py-2 text-xs text-ink-secondary",
            "transition-colors duration-fast hover:border-line-strong hover:text-ink",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
          )}
        >
          <ChevronDown aria-hidden="true" className="size-3.5 rotate-180 text-ink-muted" />
          Show earlier context ({collapsedCount} more)
        </button>
      )}

      <ol className="space-y-5">
        {visible.map((row) => {
          if (row.kind === "customer") {
            return (
              <li key={row.id} className="animate-fade-in">
                <RoleLabel time={row.time}>{customerName}</RoleLabel>
                <div className="flex">
                  <div className="max-w-[92%] rounded-2xl rounded-tl-md border border-line bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed text-ink md:max-w-[80%]">
                    {row.text}
                  </div>
                </div>
              </li>
            );
          }

          if (row.kind === "system") {
            const isEscalation = row.event === "escalation";
            return (
              <li key={row.id} className="animate-fade-in py-0.5">
                <div className="flex items-center gap-2.5">
                  <span className="h-px flex-1 bg-line" />
                  <span
                    className={cn(
                      "inline-flex min-w-0 items-center gap-1.5 text-[11px]",
                      isEscalation ? "font-medium text-accent-ink" : "text-ink-muted",
                    )}
                  >
                    {isEscalation && <Ticket aria-hidden="true" className="size-3 shrink-0" />}
                    <span className="truncate">{row.text}</span>
                    <span aria-hidden="true" className="shrink-0 opacity-70">
                      · {row.time}
                    </span>
                  </span>
                  <span className="h-px flex-1 bg-line" />
                </div>
              </li>
            );
          }

          const badge = REPLY_BADGE[row.reply.kind];
          return (
            <li key={row.id} className="animate-fade-in">
              <RoleLabel time={row.time}>Northstar Desk assistant</RoleLabel>
              <div className="rounded-card border border-line bg-surface-1 p-4 md:p-5">
                <div className="mb-3 flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-control border border-accent-border bg-accent-soft"
                  >
                    <LogoMark className="size-5" />
                  </span>
                  <Badge variant={badge.variant}>{badge.label(row.reply)}</Badge>
                </div>
                <div className="md:pl-11">
                  <AiReplyBody reply={row.reply} citations={row.citations} />
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
