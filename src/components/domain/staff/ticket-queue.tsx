"use client";

import { Search, Ticket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ApiTicketCounts } from "@/lib/api/client";
import {
  formatRelativeTime,
  formatTicketTime,
  type StaffTicketSummary,
} from "@/lib/staff/ticket-view";
import { STATUS_OPTIONS, type TicketStatus } from "@/lib/support/tickets";

interface TicketQueueProps {
  /** Already filtered/paginated by the server. */
  tickets: StaffTicketSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  query: string;
  onQueryChange: (value: string) => void;
  statusFilter: TicketStatus | "all";
  onStatusFilterChange: (value: TicketStatus | "all") => void;
  /** First load: no rows yet → skeleton. */
  loading: boolean;
  /** Refresh in flight over existing rows → dim + spinner, keep list. */
  searching: boolean;
  error: boolean;
  onRetry: () => void;
  counts: ApiTicketCounts | null;
  total: number;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

function QueueSkeleton() {
  return (
    <div className="space-y-3 p-4" aria-hidden="true">
      {[0, 1, 2].map((row) => (
        <div key={row} className="rounded-card border border-line bg-surface-1 p-4">
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="mt-3 h-4 w-4/5" />
          <Skeleton className="mt-2 h-3.5 w-3/5" />
        </div>
      ))}
    </div>
  );
}

/**
 * Escalation queue — a macOS-style source list: full-bleed rows,
 * hairline separators, accent selection bar, server-side search/filter,
 * and honest pagination. Loading, error, empty, and no-match states are
 * distinct; a refresh dims the existing rows instead of flashing
 * skeletons over them.
 */
export function TicketQueue({
  tickets,
  selectedId,
  onSelect,
  query,
  onQueryChange,
  statusFilter,
  onStatusFilterChange,
  loading,
  searching,
  error,
  onRetry,
  counts,
  total,
  hasMore,
  loadingMore,
  onLoadMore,
}: TicketQueueProps) {
  const hasFilters = query.trim().length > 0 || statusFilter !== "all";
  const firstLoad = loading && tickets.length === 0;

  const countEntries: Array<{
    key: TicketStatus;
    label: string;
    value: number | undefined;
  }> = [
    { key: "open", label: "open", value: counts?.OPEN },
    { key: "in_progress", label: "in progress", value: counts?.IN_PROGRESS },
    { key: "resolved", label: "resolved", value: counts?.RESOLVED },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="shrink-0 border-b border-line px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="font-display text-[15px] font-semibold tracking-tight text-ink">
            Escalation queue
          </h1>
          <div
            className="flex items-center gap-1 text-[11px] tabular-nums text-ink-muted"
            role="group"
            aria-label="Filter by status counts"
          >
            {countEntries.map((entry, index) => {
              const active = statusFilter === entry.key;
              return (
                <span key={entry.key} className="flex items-center gap-1">
                  {index > 0 && (
                    <span aria-hidden="true" className="text-ink-muted">
                      ·
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      onStatusFilterChange(active ? "all" : entry.key)
                    }
                    aria-pressed={active}
                    className={cn(
                      "rounded-control px-1.5 py-0.5 transition-colors duration-fast",
                      "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                      active
                        ? "bg-accent-soft font-medium text-accent-ink"
                        : "hover:bg-surface-2 hover:text-ink",
                    )}
                  >
                    {entry.value ?? 0} {entry.label}
                  </button>
                </span>
              );
            })}
          </div>
        </div>

        {/* Search + filter */}
        <div className="mt-3 flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted"
            />
            <Input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search tickets…"
              aria-label="Search tickets"
              className="pl-9 pr-8"
            />
            {searching && (
              <span
                role="status"
                aria-label="Searching"
                className="absolute right-3 top-1/2 size-3 -translate-y-1/2 animate-spin rounded-full border border-accent-border border-t-accent"
              />
            )}
          </div>
          <Select
            value={statusFilter}
            onChange={(event) =>
              onStatusFilterChange(event.target.value as TicketStatus | "all")
            }
            aria-label="Filter by status"
            options={[{ value: "all", label: "All statuses" }, ...STATUS_OPTIONS]}
            className="w-36 shrink-0"
          />
        </div>
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {firstLoad ? (
          <>
            <span role="status" className="sr-only">
              Loading escalation tickets…
            </span>
            <QueueSkeleton />
          </>
        ) : error ? (
          <ErrorState
            title="Couldn't load the queue"
            description="The tickets service didn't respond. Nothing was lost — try again."
            onRetry={onRetry}
          />
        ) : tickets.length === 0 ? (
          <EmptyState
            icon={<Ticket className="size-5" />}
            title={hasFilters ? "No tickets match" : "The queue is clear"}
            description={
              hasFilters
                ? "Try a different search or clear the filters to see every escalation."
                : "New escalations from the customer workspace will appear here."
            }
            action={
              hasFilters ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    onQueryChange("");
                    onStatusFilterChange("all");
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul
            className={cn(
              "divide-y divide-line transition-opacity duration-fast",
              searching && "pointer-events-none opacity-60",
            )}
          >
            {tickets.map((ticket, index) => {
              const selected = ticket.id === selectedId;
              return (
                <li
                  key={ticket.id}
                  className="animate-fade-in"
                  style={{ animationDelay: `${Math.min(index, 10) * 20}ms` }}
                >
                  <button
                    type="button"
                    aria-current={selected ? "true" : undefined}
                    onClick={() => onSelect(ticket.id)}
                    className={cn(
                      "relative w-full px-4 py-3 text-left transition-colors duration-fast",
                      "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/40",
                      selected
                        ? "bg-accent-soft/60"
                        : "hover:bg-surface-2",
                    )}
                  >
                    {/* Accent selection bar (macOS source-list idiom) */}
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute inset-y-0 left-0 w-[3px] transition-opacity duration-fast",
                        selected ? "bg-accent opacity-100" : "opacity-0",
                      )}
                    />

                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-medium text-ink-secondary">
                        {ticket.id}
                      </span>
                      <span className="flex items-center gap-1.5">
                        {ticket.priority === "high" && (
                          <Badge variant="accent" className="px-2 py-0 text-[10px] uppercase">
                            High
                          </Badge>
                        )}
                        <StatusBadge status={ticket.status} />
                      </span>
                    </div>

                    <p
                      className={cn(
                        "mt-1.5 text-sm font-medium leading-snug",
                        ticket.status === "resolved" ? "text-ink-muted" : "text-ink",
                      )}
                    >
                      {ticket.summary}
                    </p>

                    <p className="mt-1 flex items-center gap-1.5 truncate text-xs text-ink-secondary">
                      <span className="truncate">{ticket.customer.name}</span>
                      <span aria-hidden="true" className="shrink-0 text-ink-muted">
                        ·
                      </span>
                      <span
                        className="shrink-0 text-ink-muted"
                        title={formatTicketTime(ticket.createdAtIso)}
                      >
                        {formatRelativeTime(ticket.createdAtIso)}
                      </span>
                    </p>

                    <p className="mt-1 truncate text-[11px] text-ink-muted">
                      {ticket.escalationReason}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Pagination / honest queue count */}
      {!loading && !error && (
        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-line px-4 py-2.5">
          <span className="text-[11px] tabular-nums text-ink-muted">
            {tickets.length} of {total}
          </span>
          {hasMore && (
            <Button
              variant="secondary"
              size="sm"
              loading={loadingMore}
              onClick={onLoadMore}
            >
              Load more
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
