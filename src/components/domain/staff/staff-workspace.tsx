"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { TopNavigation } from "@/components/layout/top-navigation";
import { ModeBanner } from "@/components/layout/mode-banner";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { KnowledgePanel } from "@/components/domain/knowledge/knowledge-library";
import { cn } from "@/lib/utils";
import { TicketQueue } from "./ticket-queue";
import { TicketDetail } from "./ticket-detail";
import { StaffAuthGate } from "./staff-auth-gate";
import {
  api,
  ApiError,
  toApiStatus,
  toUiStatus,
  type ApiStaffUser,
  type ApiTicketCounts,
  type ApiTicketStatus,
} from "@/lib/api/client";
import { clearToken, getToken } from "@/lib/staff/session";
import {
  toStaffDetail,
  toStaffSummary,
  type StaffTicketDetail,
  type StaffTicketSummary,
} from "@/lib/staff/ticket-view";
import {
  STATUS_LABEL,
  type TicketStatus,
} from "@/lib/support/tickets";

const PAGE_SIZE = 50;

/** Staff auth state machine: probing the stored token → gate → workspace. */
type AuthState =
  | { phase: "checking" }
  | { phase: "signed-out" }
  | { phase: "signed-in"; user: ApiStaffUser };

function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

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
 * Staff workspace — Phase 10 + staff authentication (Phase 11).
 *
 * Access requires a signed-in staff account: first run opens the
 * create-account screen, after that the stored bearer token is verified
 * against /auth/me. Any 401 from a ticket call (expired/revoked token)
 * drops the workspace back to the sign-in gate. The signed-in user's
 * name is used for the header identity and as the status-change actor.
 *
 * Queue, detail, and lifecycle status are read from and written to the
 * Phase 5 ticket API. The server is authoritative: no status is changed
 * locally before a successful response, and stale writes are rejected.
 */
export function SupportStaffWorkspace() {
  const [authState, setAuthState] = useState<AuthState>({ phase: "checking" });
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
  const [tab, setTab] = useState<"queue" | "knowledge">("queue");

  const listSeqRef = useRef(0);
  const detailSeqRef = useRef(0);
  const { toast } = useToast();

  const authed = authState.phase === "signed-in";
  const staffName = authState.phase === "signed-in" ? authState.user.name : "staff";

  // Verify the stored token on mount; expired/unknown → sign-in gate.
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setAuthState({ phase: "signed-out" });
      return;
    }
    api.auth
      .me()
      .then((user) => {
        if (!cancelled) setAuthState({ phase: "signed-in", user });
      })
      .catch(() => {
        if (!cancelled) {
          clearToken();
          setAuthState({ phase: "signed-out" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAuthenticated = useCallback((user: ApiStaffUser) => {
    setAuthState({ phase: "signed-in", user });
  }, []);

  const handleSignOut = useCallback(async () => {
    // Best-effort server invalidation; the token is dropped locally
    // regardless so a failed call can never trap the user inside.
    try {
      await api.auth.logout();
    } catch {
      // Token may already be invalid — clearing below is what matters.
    }
    clearToken();
    setAuthState({ phase: "signed-out" });
  }, []);

  const fetchPage = useCallback(
    async (offset: number, append: boolean) => {
      if (!authed) return;
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
      } catch (fetchError) {
        if (seq !== listSeqRef.current) return;
        if (isAuthError(fetchError)) {
          // Session expired or revoked — back to the sign-in gate.
          clearToken();
          setAuthState({ phase: "signed-out" });
          return;
        }
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
    [authed, query, statusFilter, toast],
  );

  // Server-side search (debounced) and status filtering.
  useEffect(() => {
    if (!authed) return;
    const timer = window.setTimeout(
      () => void fetchPage(0, false),
      query.trim() ? 300 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [authed, fetchPage, query]);

  useEffect(
    () => () => {
      listSeqRef.current += 1;
      detailSeqRef.current += 1;
    },
    [],
  );

  const fetchDetail = useCallback(
    async (id: string) => {
      if (!authed) return;
      const seq = ++detailSeqRef.current;
      setDetailLoading(true);
      setDetailError(false);
      try {
        const response = await api.tickets.get(id);
        if (seq !== detailSeqRef.current) return;
        setDetail(toStaffDetail(response));
      } catch (fetchError) {
        if (seq !== detailSeqRef.current) return;
        if (isAuthError(fetchError)) {
          clearToken();
          setAuthState({ phase: "signed-out" });
          return;
        }
        setDetail(null);
        setDetailError(true);
      } finally {
        if (seq === detailSeqRef.current) setDetailLoading(false);
      }
    },
    [authed],
  );

  useEffect(() => {
    if (!selectedId || !authed) {
      if (!authed) {
        detailSeqRef.current += 1;
        setDetail(null);
        setDetailLoading(false);
        setDetailError(false);
      }
      return;
    }
    void fetchDetail(selectedId);
  }, [authed, fetchDetail, selectedId]);

  const handleSelect = useCallback((id: string) => {
    setSelectedId(id);
    setMobileView("detail");
    setStaleNotice(null);
  }, []);

  const handleStatusChange = useCallback(
    async (id: string, status: TicketStatus, expected: TicketStatus) => {
      if (!authed || statusPending || status === expected) return;

      setStatusPending(true);
      setStaleNotice(null);
      try {
        const response = await api.tickets.setStatus(
          id,
          toApiStatus(status),
          staffName,
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
          description: `${id} · updated by ${staffName}`,
          tone: "success",
        });

        // The queue counts and filtered membership must come from the
        // server, especially when the current filter excludes the new state.
        void fetchPage(0, false);
      } catch (updateError) {
        if (isAuthError(updateError)) {
          clearToken();
          setAuthState({ phase: "signed-out" });
          return;
        }
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
    [authed, fetchDetail, fetchPage, staffName, statusPending, toast],
  );

  const handleLoadMore = useCallback(() => {
    if (loading || loadingMore || tickets.length >= total) return;
    void fetchPage(tickets.length, true);
  }, [fetchPage, loading, loadingMore, tickets.length, total]);

  const handleSendReply = useCallback(
    async (ticketId: string, message: string, channel: "smtp" | "gmail") => {
      if (!authed) throw new ApiError("Sign in to send replies.", { status: 401 });
      const reply = await api.tickets.sendReply(ticketId, message, channel);
      if (channel === "gmail") {
        toast({
          title: "Gmail compose opened",
          description:
            "Press Send in the Gmail tab to deliver the reply — the message is recorded with the ticket.",
          tone: "info",
        });
      } else {
        toast({
          title: reply.emailDispatched
            ? `Reply sent to ${reply.sentTo}`
            : "Reply stored — email not delivered",
          description: reply.emailDispatched
            ? `${ticketId} · by ${reply.staffName}`
            : (reply.dispatchNote ?? "The message is recorded with the ticket."),
          tone: reply.emailDispatched ? "success" : "info",
        });
      }
      // Refresh the stored reply history from the server (never local state).
      void fetchDetail(ticketId);
    },
    [authed, fetchDetail, toast],
  );

  // Probing the stored token — quiet full-screen spinner.
  if (authState.phase === "checking") {
    return (
      <div className="flex h-dvh items-center justify-center bg-canvas">
        <span
          role="status"
          aria-label="Checking sign-in"
          className="size-6 animate-spin rounded-full border-2 border-accent-border border-t-accent"
        />
      </div>
    );
  }

  // Not signed in (or the session expired) — the auth gate owns the page.
  if (authState.phase === "signed-out") {
    return <StaffAuthGate onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopNavigation
        navItems={[
          { label: "Customer chat", href: "/" },
          { label: "Staff queue", href: "/staff", active: true },
        ]}
        user={{ name: authState.user.name }}
        actions={
          <Button variant="ghost" size="sm" onClick={() => void handleSignOut()}>
            <LogOut aria-hidden="true" />
            <span className="hidden sm:inline">Sign out</span>
            <span className="sr-only sm:hidden">Sign out</span>
          </Button>
        }
      />
      <ModeBanner />

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Workspace tabs — the knowledge base lives inside the staff queue */}
        <div className="shrink-0 border-b border-line bg-canvas/85 backdrop-blur-md">
          <div
            role="tablist"
            aria-label="Staff workspace sections"
            className="mx-auto flex w-full max-w-[1600px] items-center gap-1 px-4 md:px-6"
          >
            {(
              [
                { id: "queue", label: "Queue" },
                { id: "knowledge", label: "Knowledge base" },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`staff-tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`staff-panel-${item.id}`}
                onClick={() => setTab(item.id)}
                className={cn(
                  "relative rounded-control px-3 py-2.5 text-sm font-medium transition-colors duration-fast",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                  tab === item.id
                    ? "text-ink"
                    : "text-ink-secondary hover:text-ink",
                )}
              >
                {item.label}
                {tab === item.id && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent"
                  />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Queue tab — kept mounted so the list state survives tab switches */}
        <div
          role="tabpanel"
          id="staff-panel-queue"
          aria-labelledby="staff-tab-queue"
          className={cn("min-h-0 flex-1 overflow-hidden", tab !== "queue" && "hidden")}
        >
          <div className="mx-auto grid h-full w-full max-w-[1600px] grid-cols-1 grid-rows-[minmax(0,1fr)] lg:grid-cols-[22rem_minmax(0,1fr)]">
            {/* Queue panel — full screen below lg, fixed rail above */}
            <div
              className={
                mobileView === "queue"
                  ? "flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-line"
                  : "hidden min-h-0 min-w-0 flex-col overflow-hidden border-r border-line lg:flex"
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
                  ? "flex min-h-0 min-w-0 flex-col overflow-hidden"
                  : "hidden min-h-0 min-w-0 flex-col overflow-hidden lg:flex"
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
                  onSendReply={handleSendReply}
                  staffName={authState.user.name}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Knowledge tab — fresh documents on every open */}
        {tab === "knowledge" && <KnowledgePanel />}
      </main>
    </div>
  );
}
