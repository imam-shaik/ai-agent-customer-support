"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { TopNavigation } from "@/components/layout/top-navigation";
import { ModeBanner } from "@/components/layout/mode-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { WelcomeState } from "./welcome-state";
import { MessageTimeline, type ChatMessage, type FeedbackValue } from "./message-timeline";
import { Composer } from "./composer";
import { EvidenceSheet } from "./evidence-sheet";
import { SourcesRail, type MyTicketRow } from "./sources-rail";
import { Drawer } from "@/components/ui/drawer";
import {
  EscalationDialog,
  TicketChip,
  ticketRecordFromActive,
  ticketRecordFromDetail,
  type ContactInfo,
  type TicketRecord,
} from "./escalation-dialog";
import {
  api,
  ApiError,
  type AgentReply,
  type ApiChatHistory,
  type ApiCitation,
} from "@/lib/api/client";
import {
  createSession,
  isRetryableError,
  loadConversation,
  makeClientRequestId,
  saveFeedback,
  sendTurn,
} from "@/lib/api/chat-turn";
import { SUPPORT_TOPICS } from "@/lib/support/knowledge";

const CONVERSATION_KEY = "northstar.conversationId";
const API_ERROR_TEXT =
  "The support service didn't respond in time. Nothing was lost — your message is still here.";

function nowTime() {
  return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatTime(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return nowTime();
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function errorReplyFor(error: unknown): AgentReply {
  if (error instanceof ApiError) {
    if (error.status === 503) {
      return {
        kind: "error",
        text: "Support answers are temporarily unavailable. Your message is saved and nothing was sent twice. Please try again shortly.",
      };
    }
    if (error.status === 502) {
      return {
        kind: "error",
        text: "The assistant couldn't complete this answer safely. Your message is saved — please try again.",
      };
    }
    if (error.status === 404) {
      return {
        kind: "error",
        text: "This conversation is no longer available. Please try your message again — a new conversation will start.",
      };
    }
    if (error.status === 409) {
      return {
        kind: "error",
        text: "This request conflicts with an earlier one. Please reload the conversation and try again.",
      };
    }
  }
  return { kind: "error", text: API_ERROR_TEXT };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function escalationReasonFor(reply: AgentReply | null): string {
  if (!reply) return "Escalated from customer conversation";
  if (reply.kind === "unsupported") {
    return "No supporting evidence in approved documentation";
  }
  if (reply.kind === "uncertain") {
    return "Evidence was insufficient to confirm a complete answer";
  }
  if (reply.kind === "conflict") {
    return "Conflicting evidence in approved documentation";
  }
  return "Escalated from customer conversation";
}

function applyTurn(
  prev: ChatMessage[],
  optimisticId: string,
  turn: Awaited<ReturnType<typeof sendTurn>>,
): ChatMessage[] {
  const assistant = turn.assistantMessage;
  if (!assistant.reply) return prev;

  const reconciled = prev.map((message) =>
    message.kind === "user" && message.id === optimisticId
      ? {
          ...message,
          id: turn.userMessage.id,
          text: turn.userMessage.content,
          time: formatTime(turn.userMessage.createdAt),
          createdAt: turn.userMessage.createdAt,
          clientRequestId: turn.userMessage.clientRequestId,
        }
      : message
  );

  return [
    ...reconciled,
    {
      id: assistant.id,
      kind: "agent",
      reply: assistant.reply,
      time: formatTime(assistant.createdAt),
      createdAt: assistant.createdAt,
      feedback: assistant.feedback
        ? {
            value: assistant.feedback.rating,
            reason: assistant.feedback.reason ?? undefined,
          }
        : undefined,
    },
  ];
}

function toChatMessages(history: ApiChatHistory): ChatMessage[] {
  const messages: ChatMessage[] = [];

  for (const message of history.messages) {
    const time = formatTime(message.createdAt);
    if (message.role === "user") {
      messages.push({
        id: message.id,
        kind: "user",
        text: message.content,
        time,
        createdAt: message.createdAt,
        clientRequestId: message.clientRequestId,
      });
    } else if (message.role === "system") {
      messages.push({ id: message.id, kind: "system", text: message.content, time });
    } else if (message.reply) {
      messages.push({
        id: message.id,
        kind: "agent",
        reply: message.reply,
        time,
        createdAt: message.createdAt,
        feedback: message.feedback
          ? {
              value: message.feedback.rating,
              reason: message.feedback.reason ?? undefined,
            }
          : undefined,
      });
    } else {
      // Never synthesize an answer for a legacy/broken row.
      messages.push({
        id: message.id,
        kind: "system",
        text: "This earlier reply could not be displayed.",
        time,
      });
    }
  }

  const last = history.messages[history.messages.length - 1];
  if (last?.role === "user") {
    messages.push({
      id: `unanswered-${last.id}`,
      kind: "agent",
      reply: {
        kind: "error",
        text: "This message hasn't been answered yet. You can try again.",
      },
      time: formatTime(last.createdAt),
      failedTurn: {
        content: last.content,
        clientRequestId: last.clientRequestId,
      },
    });
  }

  return messages;
}

const ANNOUNCEMENTS: Record<AgentReply["kind"], (reply: AgentReply) => string> = {
  grounded: (reply) =>
    reply.kind === "grounded"
      ? `Grounded answer received, supported by ${reply.citations.length} source${reply.citations.length === 1 ? "" : "s"}.`
      : "",
  clarifying: () => "A clarifying question was received.",
  guard: () =>
    "The request to override instructions was declined; no internal details were revealed and the support workflow continued.",
  conflict: () =>
    "The retrieved documents conflict; the assistant did not guess and offered escalation to a human.",
  unsupported: () => "No supporting evidence was found; escalation was offered.",
  uncertain: () =>
    "Related documentation was found, but it was not enough to confirm a complete answer; escalation was offered.",
  escalation_offer: () => "The assistant offered to create a support ticket.",
  error: () => "The support service did not respond. A retry option is available.",
};

/**
 * Customer support workspace — Phase 9.
 *
 * Real sessions and turns (Phase 5–8B backend), request-id idempotent
 * retries, server-backed history, snapshot citations, real escalation and
 * feedback. The UI contract is the approved Phase 3 one; only the data
 * seam, the `uncertain` card, and the honest loading state changed.
 */
export function SupportWorkspace() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  /** Sources drawer (below xl screens). */
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [documentTitles, setDocumentTitles] = useState<Record<string, string>>({});
  const [documentCount, setDocumentCount] = useState<number | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState(SUPPORT_TOPICS[0].id);
  const [escalationOpen, setEscalationOpen] = useState(false);
  const [evidence, setEvidence] = useState<{ citations: ApiCitation[]; context: string } | null>(
    null,
  );
  const [contact, setContact] = useState<ContactInfo>({ name: "", email: "", phone: "" });
  const [ticket, setTicket] = useState<TicketRecord | null>(null);
  /** All tickets raised from THIS conversation (server data, newest first). */
  const [myTickets, setMyTickets] = useState<MyTicketRow[] | null>(null);

  const { toast } = useToast();
  const conversationRef = useRef<string | null>(null);
  const runIdRef = useRef(0);
  const counterRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  /** Aborts the in-flight turn (Esc / Stop). Client-side cancel only: the
   *  backend may still finish and persist, and a retry replays it. */
  const abortRef = useRef<AbortController | null>(null);

  const uid = useCallback(() => {
    counterRef.current += 1;
    return `m-${counterRef.current}`;
  }, []);

  // Restore a stored conversation and the real document list on mount.
  useEffect(() => {
    let alive = true;

    void api.documents
      .list()
      .then((documents) => {
        if (!alive) return;
        setDocumentTitles(
          Object.fromEntries(documents.map((document) => [document.id, document.title]))
        );
        setDocumentCount(
          documents.filter((document) => document.knowledgeStatus === "approved").length
        );
      })
      .catch(() => {
        // Auxiliary only — chatting must never depend on this fetch.
      });

    const stored =
      typeof window === "undefined"
        ? null
        : window.sessionStorage.getItem(CONVERSATION_KEY);

    if (!stored) {
      setHydrating(false);
      return () => {
        alive = false;
      };
    }

    void loadConversation(stored)
      .then((history) => {
        if (!alive) return;
        conversationRef.current = stored;
        setConversationId(stored);
        setMessages(toChatMessages(history));
        if (history.activeTicket) {
          setTicket(ticketRecordFromActive(history.activeTicket));
        }
      })
      .catch(() => {
        if (!alive) return;
        window.sessionStorage.removeItem(CONVERSATION_KEY);
        conversationRef.current = null;
        setConversationId(null);
      })
      .finally(() => {
        if (alive) setHydrating(false);
      });

    return () => {
      alive = false;
      runIdRef.current += 1;
    };
  }, []);

  // Keep the conversation pinned to the newest content. The welcome
  // screen must stay at the top — never auto-scroll it out of view.
  useEffect(() => {
    if (hydrating || messages.length === 0) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, hydrating]);

  const busy = thinking || hydrating;
  const hasConversation = messages.length > 0;

  const lastUserQuestion = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.kind === "user") return message.text;
    }
    return "";
  }, [messages]);

  const latestReply = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.kind === "agent") return message.reply;
    }
    return null;
  }, [messages]);

  const latestCitations = useMemo<ApiCitation[]>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.kind === "agent" && message.reply.kind === "grounded") {
        return message.reply.citations;
      }
    }
    return [];
  }, [messages]);

  const announcement = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.kind === "agent") return ANNOUNCEMENTS[message.reply.kind](message.reply);
      if (message.kind === "system") return message.text;
    }
    return "";
  }, [messages]);

  /** Run one real agent turn; retries reuse the same request id. */
  const runTurn = useCallback(
    async (
      text: string,
      options?: {
        appendUser?: boolean;
        /** null = legacy turn with no id (backend tail-reuse path). */
        clientRequestId?: string | null;
        userMessageId?: string;
      },
    ) => {
      const runId = ++runIdRef.current;
      const alive = () => runIdRef.current === runId;

      const clientRequestId =
        options?.clientRequestId === null
          ? undefined
          : (options?.clientRequestId ?? makeClientRequestId());
      const optimisticId = options?.userMessageId ?? uid();

      // One controller per run: Esc/Stop aborts the WAIT (never a backend
      // contract change — the turn may still persist and a retry replays it).
      const controller = new AbortController();
      abortRef.current = controller;

      if (options?.appendUser !== false) {
        setMessages((prev) => [
          ...prev,
          {
            id: optimisticId,
            kind: "user",
            text,
            time: nowTime(),
            clientRequestId: clientRequestId ?? null,
          },
        ]);
      }

      setThinking(true);
      try {
        let activeConversation = conversationRef.current;
        if (!activeConversation) {
          activeConversation = await createSession();
          if (!alive()) return;
          conversationRef.current = activeConversation;
          setConversationId(activeConversation);
          window.sessionStorage.setItem(CONVERSATION_KEY, activeConversation);
        }

        const turn = await sendTurn(
          activeConversation,
          text,
          clientRequestId,
          controller.signal,
        );
        if (!alive()) return;

        setMessages((prev) => applyTurn(prev, optimisticId, turn));
      } catch (error) {
        if (!alive()) return;

        // The customer cancelled (Esc / Stop): calm cancelled card with
        // idempotent Try again (replays a completed turn) + Edit message.
        if (controller.signal.aborted || isAbortError(error)) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              kind: "agent",
              reply: { kind: "error", text: "You cancelled this response." },
              cancelled: true,
              time: nowTime(),
              failedTurn: {
                content: text,
                clientRequestId: clientRequestId ?? null,
              },
            },
          ]);
          return;
        }

        if (error instanceof ApiError && error.status === 404) {
          window.sessionStorage.removeItem(CONVERSATION_KEY);
          conversationRef.current = null;
          setConversationId(null);
        }

        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            kind: "agent",
            reply: errorReplyFor(error),
            time: nowTime(),
            failedTurn: isRetryableError(error)
              ? { content: text, clientRequestId: clientRequestId ?? null }
              : undefined,
          },
        ]);
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        if (alive()) setThinking(false);
      }
    },
    [uid]
  );

  /** Esc / Stop: stop WAITING for the in-flight response. */
  const cancelTurn = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Esc cancels the running response — but never steals Esc from open
  // overlays (dialogs / drawers close themselves first).
  useEffect(() => {
    if (!thinking) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (escalationOpen || sourcesOpen || evidence !== null) return;
      event.preventDefault();
      cancelTurn();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [thinking, escalationOpen, sourcesOpen, evidence, cancelTurn]);

  /** Prefill the composer with a previous question for an edited resend. */
  const handleEditQuery = useCallback((text: string) => {
    setInput(text);
    requestAnimationFrame(() => {
      const el = document.getElementById("composer-input") as HTMLTextAreaElement | null;
      if (!el) return;
      el.focus();
      const end = el.value.length;
      el.setSelectionRange(end, end);
    });
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (text.length < 2 || busy) return;
    setInput("");
    void runTurn(text);
  }, [input, busy, runTurn]);

  /** Retry one failed turn with its original request id. */
  const handleRetry = useCallback(
    (messageId: string) => {
      if (busy) return;
      const index = messages.findIndex(
        (message) =>
          message.id === messageId &&
          message.kind === "agent" &&
          message.reply.kind === "error"
      );
      if (index < 0) return;

      const failed = messages[index];
      if (failed.kind !== "agent" || failed.reply.kind !== "error" || !failed.failedTurn) {
        return;
      }
      const { content, clientRequestId } = failed.failedTurn;

      let userMessageId: string | undefined;
      for (let i = index - 1; i >= 0; i -= 1) {
        const candidate = messages[i];
        if (candidate.kind === "user" && candidate.text === content) {
          userMessageId = candidate.id;
          break;
        }
      }

      setMessages((prev) => prev.filter((message) => message.id !== messageId));
      void runTurn(content, {
        appendUser: userMessageId === undefined,
        clientRequestId,
        userMessageId,
      });
    },
    [busy, messages, runTurn]
  );

  const handleFeedback = useCallback(
    (id: string, value: FeedbackValue, reason?: string) => {
      const target = messages.find((message) => message.id === id);
      if (!target || target.kind !== "agent" || target.reply.kind === "error") return;

      const previous = target.feedback;
      setMessages((prev) =>
        prev.map((message) =>
          message.id === id && message.kind === "agent"
            ? { ...message, feedback: { value, reason } }
            : message
        )
      );

      void saveFeedback(id, value, reason).catch((error) => {
        // 409 means the server already has feedback — keep the recorded state.
        if (error instanceof ApiError && error.status === 409) return;
        setMessages((prev) =>
          prev.map((message) =>
            message.id === id && message.kind === "agent"
              ? { ...message, feedback: previous }
              : message
          )
        );
        toast({
          title: "Couldn't save feedback",
          description: "Please try again.",
          tone: "danger",
        });
      });
    },
    [messages, toast]
  );

  /** Fetch every ticket raised from THIS conversation (newest first). */
  const refreshMyTickets = useCallback(async () => {
    if (!conversationId) {
      setMyTickets(null);
      return;
    }
    try {
      const listing = await api.tickets.listForConversation(conversationId);
      setMyTickets(listing.items);
    } catch {
      // Quiet: the rail keeps its last known rows; the ticket chip and
      // staff queue remain the authoritative surfaces.
    }
  }, [conversationId]);

  useEffect(() => {
    void refreshMyTickets();
  }, [refreshMyTickets]);

  /** Open one raised ticket's full record in the escalation dialog. */
  const handleOpenTicket = useCallback(
    async (row: MyTicketRow) => {
      try {
        const detail = await api.tickets.get(row.id);
        setTicket(ticketRecordFromDetail(detail));
        setEscalationOpen(true);
      } catch {
        toast({
          title: "Ticket unavailable",
          description: `${row.id} could not be loaded. It remains stored on the server.`,
          tone: "danger",
        });
      }
    },
    [toast],
  );

  const handleTicketCreated = useCallback(
    (created: TicketRecord) => {
      setTicket(created);
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          kind: "system",
          text: `Ticket ${created.id} created · ${created.contextMessages} message${created.contextMessages === 1 ? "" : "s"} attached`,
          ticketId: created.id,
          time: nowTime(),
        },
      ]);
      // The 'my tickets' section now has a new row to show.
      void refreshMyTickets();
    },
    [uid, refreshMyTickets]
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <TopNavigation
        navItems={[
          { label: "Customer chat", href: "/", active: true },
          { label: "Knowledge base", href: "/knowledge" },
          { label: "Staff queue", href: "/staff" },
        ]}
      />
      <ModeBanner />

      <div className="flex w-full min-h-0 flex-1 flex-col lg:flex-row">
        {/* ---------- Conversation column — the hero ---------- */}
        <section
          aria-label="Support conversation"
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
        >
          {/* Conversation header */}
          <header className="shrink-0 border-b border-line bg-canvas/85 backdrop-blur-md">
            <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 md:px-6">
              <div className="min-w-0">
                <h1 className="truncate font-display text-[15px] font-semibold tracking-tight text-ink">
                  Support conversation
                </h1>
                <p className="mt-0.5 text-[11px] text-ink-muted">
                  Northstar Desk · answers from approved documentation
                </p>
              </div>

              <div className="ml-auto flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="lg:hidden"
                  onClick={() => setSourcesOpen(true)}
                  aria-label="Show sources for the latest answer"
                >
                  <FileText aria-hidden="true" className="size-3.5" />
                  Sources
                </Button>
                {ticket && <TicketChip ticket={ticket} onClick={() => setEscalationOpen(true)} />}
                <span
                  className="text-[11px] tabular-nums text-ink-muted"
                  aria-live="polite"
                >
                  {hydrating
                    ? "Restoring…"
                    : hasConversation
                      ? `${messages.length} message${messages.length === 1 ? "" : "s"}`
                      : "Ready"}
                </span>
              </div>
            </div>
          </header>

          {/* Timeline */}
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
              {hydrating ? (
                <div className="rounded-card border border-line bg-surface-1 p-4 text-sm text-ink-muted">
                  Restoring your conversation…
                </div>
              ) : hasConversation ? (
                <MessageTimeline
                  messages={messages}
                  thinking={thinking}
                  documentTitles={documentTitles}
                  ticketId={ticket?.id}
                  onFeedback={handleFeedback}
                  onRetry={handleRetry}
                  onEscalate={() => setEscalationOpen(true)}
                  onPick={(question) => void runTurn(question)}
                  onOpenTicket={() => setEscalationOpen(true)}
                  onInspectEvidence={(citations, context) => setEvidence({ citations, context })}
                  onStop={cancelTurn}
                  onEditQuery={thinking ? undefined : handleEditQuery}
                />
              ) : (
                <WelcomeState
                  topics={SUPPORT_TOPICS}
                  selectedTopicId={selectedTopicId}
                  onSelectTopic={setSelectedTopicId}
                  onAsk={(question) => void runTurn(question)}
                />
              )}
            </div>
          </div>

          {/* Composer */}
          <div className="shrink-0 border-t border-line bg-canvas/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md">
            <div className="mx-auto w-full max-w-3xl px-4 py-4 md:px-6">
              <Composer value={input} onChange={setInput} onSend={handleSend} busy={busy} />
              <p className="mt-2 text-center text-[11px] leading-relaxed text-ink-muted">
                Responses are generated from Northstar Desk&apos;s approved documentation
              </p>
            </div>
          </div>
        </section>

        {/* ---------- Sources rail (real retrieval data for the latest turn) ---------- */}
        <aside
          aria-label="Sources for the latest answer"
          className="hidden min-h-0 w-80 shrink-0 border-l border-line bg-surface-2/40 lg:block"
        >
          <SourcesRail
            messages={messages}
            thinking={thinking}
            documentTitles={documentTitles}
            documentCount={documentCount}
            myTickets={myTickets ?? undefined}
            onOpenTicket={(row) => void handleOpenTicket(row)}
            onInspectEvidence={(citations, context) => setEvidence({ citations, context })}
          />
        </aside>
      </div>

      {/* ---------- Sources drawer (below lg) ---------- */}
      <Drawer
        open={sourcesOpen}
        onOpenChange={setSourcesOpen}
        side="right"
        title="Sources"
        description="What the assistant searched for your latest question."
      >
        <SourcesRail
          messages={messages}
          thinking={thinking}
          documentTitles={documentTitles}
          documentCount={documentCount}
          showHeader={false}
          myTickets={myTickets ?? undefined}
          onOpenTicket={(row) => void handleOpenTicket(row)}
          onInspectEvidence={(citations, context) => {
            setEvidence({ citations, context });
            setSourcesOpen(false);
          }}
          className="-mx-5 -my-5 min-h-[60vh]"
        />
      </Drawer>

      {/* ---------- Evidence sheet (on-demand inspection) ---------- */}
      <EvidenceSheet
        open={evidence !== null}
        onOpenChange={(open) => {
          if (!open) setEvidence(null);
        }}
        citations={evidence?.citations ?? []}
        context={evidence?.context}
      />

      {/* ---------- Escalation flow ---------- */}
      <EscalationDialog
        open={escalationOpen}
        onOpenChange={setEscalationOpen}
        conversationId={conversationId}
        originalQuestion={lastUserQuestion}
        contextMessages={messages.length}
        escalationReason={escalationReasonFor(latestReply)}
        contact={contact}
        onContactChange={setContact}
        ticket={ticket}
        onCreated={handleTicketCreated}
      />

      {/* ---------- Screen-reader announcements ---------- */}
      <div aria-live="polite" role="status" className="sr-only">
        {announcement}
      </div>
    </div>
  );
}
