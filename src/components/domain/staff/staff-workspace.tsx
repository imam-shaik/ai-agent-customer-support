"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TopNavigation } from "@/components/layout/top-navigation";
import { ModeBanner } from "@/components/layout/mode-banner";
import { useToast } from "@/components/ui/toast";
import { TicketQueue } from "./ticket-queue";
import { TicketDetail } from "./ticket-detail";
import {
  api,
  ApiError,
  toApiStatus,
  toUiStatus,
  type ApiTicketCounts,
  type ApiTicketStatus,
} from "@/lib/api/client";
import {
  toStaffDetail,
  toStaffSummary,
  type StaffTicketDetail,
  type StaffTicketSummary,
} from "@/lib/staff/ticket-view";
import {
  STAFF_MEMBER,
  STATUS_LABEL,
  type TicketStatus,
} from "@/lib/support/tickets";

const PAGE_SIZE = 50;

function conflictMessage(error: ApiError): string {
  const details = error.details as { currentStatus?: string } | null;
  const current = details?.currentStatus;
  const label =
    current && ["OPEN", "IN_PROGRESS", "RESOLVED"].includes(current)
      ? STATUS_LABEL[toUiStatus(current as ApiTicketStatus)]
      : "another status";
  return `Another staff member changed this ticket to ${label}. The latest server state has been loaded.`;
}

function updateErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return conflictMessage(error);
    if (error.status === 404) {
      return "This ticket no longer exists. The queue has been refreshed.";
    }
    if (error.status === 0) {
      return "Couldn't reach the ticket service. The status was not changed.";
    }
    if (error.status >= 500) {
      return "The ticket service didn't complete the change. The status was not changed.";
    }
  }
  return "The status update failed. The status was not changed.";
}

/**
 * Staff workspace — Phase 10.
 *
 * Queue, detail, and lifecycle status are read from and written to the
 * Phase 5 ticket API. The server is authoritative: no status is changed
 * locally before a successful response, and stale writes are rejected.
 */
export function SupportStaffWorkspace() {
  const [tickets, setTickets] = useState<StaffTicketSummary[]>([]);
  const [counts, setCounts] = useState<ApiTicketCounts | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<TicketStatus | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<StaffTicketDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const [statusPending, setStatusPending] = useState(false);
  const [staleNotice, setStaleNotice] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"queue" | "detail">("queue");
  const [pulseId, setPulseId] = useState<string | null>(null);

  const listSeqRef = useRef(0);
  const detailSeqRef = useRef(0);
  const { toast } = useToast();

  const fetchPage = useCallback(
    async (offset: number, append: boolean) => {
      const seq = ++listSeqRef.current;
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setError(false);
      }

      try {
        const page = await api.tickets.list({
          status: statusFilter === "all" ? undefined : toApiStatus(statusFilter),
          q: query.trim() || undefined,
          limit: PAGE_SIZE,
          offset,
        });
        if (seq !== listSeqRef.current) return;

        const incoming = page.items.map(toStaffSummary);
        setTickets((prev) => (append ? [...prev, ...incoming] : incoming));
        setCounts(page.counts);
        setTotal(page.total);

        if (!append) {
          setSelectedId((current) => {
            if (current && incoming.some((ticket) => ticket.id === current)) {
              return current;
            }
            return incoming[0]?.id ?? null;
          });
        }
      } catch {
        if (seq !== listSeqRef.current) return;
        if (append) {
          toast({
            title: "Couldn't load more tickets",
            description: "Your current results are still here. Try again.",
            tone: "danger",
          });
        } else {
          setError(true);
          setTickets([]);
          setCounts(null);
          setTotal(0);
        }
      } finally {
        if (seq === listSeqRef.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [query, statusFilter, toast],
  );

  // Server-side search (debounced) and status filtering.
  useEffect(() => {
    const timer = window.setTimeout(
      () => void fetchPage(0, false),
      query.trim() ? 300 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [fetchPage, query]);

  useEffect(
    () => () => {
      listSeqRef.current += 1;
      detailSeqRef.current += 1;
    },
    [],
  );

  const fetchDetail = useCallback(async (id: string) => {
    const seq = ++detailSeqRef.current;
    setDetailLoading(true);
    setDetailError(false);
    try {
      const response = await api.tickets.get(id);
      if (seq !== detailSeqRef.current) return;
      setDetail(toStaffDetail(response));
    } catch {
      if (seq !== detailSeqRef.current) return;
      setDetail(null);
      setDetailError(true);
    } finally {
      if (seq === detailSeqRef.current) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      detailSeqRef.current += 1;
      setDetail(null);
      setDetailLoading(false);
      setDetailError(false);
      return;
    }
    void fetchDetail(selectedId);
  }, [fetchDetail, selectedId]);

  const handleSelect = useCallback((id: string) => {
    setSelectedId(id);
    setMobileView("detail");
    setStaleNotice(null);
  }, []);

  const handleStatusChange = useCallback(
    async (id: string, status: TicketStatus, expected: TicketStatus) => {
      if (statusPending || status === expected) return;

      setStatusPending(true);
      setStaleNotice(null);
      try {
        const response = await api.tickets.setStatus(
          id,
          toApiStatus(status),
          STAFF_MEMBER,
          toApiStatus(expected),
        );

        setDetail(toStaffDetail(response));
        setTickets((prev) =>
          prev.map((ticket) => (ticket.id === id ? toStaffSummary(response) : ticket)),
        );
        setPulseId(id);
        window.setTimeout(
          () => setPulseId((current) => (current === id ? null : current)),
          2000,
        );
        toast({
          title: `Status set to ${STATUS_LABEL[status]}`,
          description: `${id} · updated by ${STAFF_MEMBER}`,
          tone: "success",
        });

        // The queue counts and filtered membership must come from the
        // server, especially when the current filter excludes the new state.
        void fetchPage(0, false);
      } catch (updateError) {
        const message = updateErrorMessage(updateError);
        setStaleNotice(message);
        toast({
          title:
            updateError instanceof ApiError && updateError.status === 404
              ? "Ticket unavailable"
              : "Status not changed",
          description: message,
          tone: "danger",
        });

        // Refresh from the server; never pretend the local choice won.
        void fetchDetail(id);
        void fetchPage(0, false);
      } finally {
        setStatusPending(false);
      }
    },
    [fetchDetail, fetchPage, statusPending, toast],
  );

  const handleLoadMore = useCallback(() => {
    if (loading || loadingMore || tickets.length >= total) return;
    void fetchPage(tickets.length, true);
  }, [fetchPage, loading, loadingMore, tickets.length, total]);

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopNavigation
        navItems={[
          { label: "Customer chat", href: "/" },
          { label: "Knowledge base", href: "/knowledge" },
          { label: "Staff queue", href: "/staff", active: true },
        ]}
        user={{ name: STAFF_MEMBER }}
      />
      <ModeBanner />

      <main className="min-h-0 flex-1">
        <div className="mx-auto grid h-full w-full max-w-[1600px] grid-cols-1 lg:grid-cols-[22rem_minmax(0,1fr)]">
          {/* Queue panel — full screen below lg, fixed rail above */}
          <div
            className={
              mobileView === "queue"
                ? "flex min-w-0 flex-col border-r border-line"
                : "hidden min-w-0 flex-col border-r border-line lg:flex"
            }
          >
            <TicketQueue
              tickets={tickets}
              selectedId={selectedId}
              onSelect={handleSelect}
              query={query}
              onQueryChange={setQuery}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              loading={loading}
              searching={loading && tickets.length > 0}
              error={error}
              onRetry={() => void fetchPage(0, false)}
              counts={counts}
              total={total}
              hasMore={tickets.length < total}
              loadingMore={loadingMore}
              onLoadMore={handleLoadMore}
            />
          </div>

          {/* Detail panel — keyed crossfade on ticket switch */}
          <div
            className={
              mobileView === "detail"
                ? "flex min-w-0 flex-col"
                : "hidden min-w-0 flex-col lg:flex"
            }
          >
            <div key={selectedId ?? "none"} className="flex min-h-0 flex-1 flex-col animate-fade-in">
              <TicketDetail
                ticket={detail}
                loading={detailLoading}
                error={detailError}
                onRetry={() => {
                  if (selectedId) void fetchDetail(selectedId);
                }}
                onStatusChange={handleStatusChange}
                statusPending={statusPending}
                staleNotice={staleNotice}
                onBack={() => setMobileView("queue")}
                pulse={pulseId === selectedId}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
