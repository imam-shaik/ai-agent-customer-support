/**
 * Frontend API client boundary — Phase 5, extended for Phase 6 (documents).
 *
 * This module is the ONLY place the frontend will talk to the FastAPI
 * backend (Phase 9 rewires the UI to it). Rules:
 *
 *  - Components never call `fetch` directly; they go through `api`.
 *  - The customer chat seam lives in `@/lib/api/chat-turn`.
 *  - Every failure is normalized into a single `ApiError` with a safe
 *    message — UI code never parses backend exception text.
 *
 * Base URL comes from NEXT_PUBLIC_API_BASE_URL (see .env.example).
 */

import type { Citation } from "@/lib/support/knowledge";
import { getToken } from "@/lib/staff/session";

const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** Error envelope returned by every backend failure (Phase 5 contract). */
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
    request_id?: string | null;
  };
}

/** Normalized error thrown by every method below. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(
    message: string,
    options: { status?: number; code?: string; details?: unknown; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.code = options.code ?? "NETWORK_ERROR";
    this.details = options.details;
    this.requestId = options.requestId ?? null;
  }
}

/* ------------------------------------------------------------------ */
/* Response types (camelCase, identical to the backend API payloads)   */
/* ------------------------------------------------------------------ */

/** Backend citation — a superset of the UI's `Citation` contract. */
export interface ApiCitation extends Citation {
  documentTitle?: string | null;
  sectionTitle?: string | null;
  snippet?: string | null;
}

/**
 * Canonical typed reply union — mirrors the backend contract exactly.
 *
 * `error` is client-side only: the backend represents failures as HTTP
 * error envelopes, never as a 200 reply. The real backend attaches
 * escalation offers to the three dead-end kinds as the `escalationOffer`
 * field; the standalone `escalation_offer` kind is kept only for
 * backward compatibility with previously stored rows.
 */
export type AgentReply =
  | { kind: "grounded"; text: string; citations: ApiCitation[] }
  | { kind: "clarifying"; text: string; options: string[] }
  | {
      kind: "unsupported";
      text: string;
      checkedDocIds: string[];
      suggestions: string[];
      escalationOffer?: string | null;
    }
  | {
      kind: "uncertain";
      text: string;
      checkedDocIds: string[];
      suggestions: string[];
      escalationOffer?: string | null;
    }
  | {
      kind: "conflict";
      text: string;
      checkedDocIds: string[];
      suggestions: string[];
      escalationOffer?: string | null;
    }
  | { kind: "guard"; text: string; options: string[] }
  | { kind: "escalation_offer"; text: string }
  | { kind: "error"; text: string };

export type ApiRole = "user" | "assistant" | "system";

export interface ApiMessage {
  id: string;
  role: ApiRole;
  content: string;
  createdAt: string;
  reply: AgentReply | null;
  citations: ApiCitation[];
  clientRequestId: string | null;
  feedback: ApiFeedback | null;
}

export interface ApiChatSession {
  conversationId: string;
  createdAt: string;
}

export interface ApiChatTurn {
  conversationId: string;
  userMessage: ApiMessage;
  assistantMessage: ApiMessage;
}

export interface ApiActiveTicket {
  id: string;
  status: ApiTicketStatus;
  summary: string;
  originalQuestion: string;
  customerName: string;
  customerEmail: string;
  customerPhone: string | null;
  createdAt: string;
  messageCount: number;
}

export interface ApiChatHistory {
  conversationId: string;
  messages: ApiMessage[];
  activeTicket: ApiActiveTicket | null;
}

/** Backend statuses are canonical UPPERCASE. */
export type ApiTicketStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED";
/** Staff UI statuses are lowercase (Phase 4 contract). */
export type UiTicketStatus = "open" | "in_progress" | "resolved";
export type ApiTicketPriority = "normal" | "high";

export interface ApiEscalationCreate {
  customerName: string;
  customerEmail: string;
  customerPhone?: string;
  summary: string;
  originalQuestion: string;
  escalationReason?: string;
  priority?: ApiTicketPriority;
}

export interface ApiTicketSummary {
  id: string;
  conversationId: string;
  customerName: string;
  customerEmail: string;
  customerPhone: string | null;
  summary: string;
  escalationReason: string;
  status: ApiTicketStatus;
  priority: ApiTicketPriority;
  createdAt: string;
  updatedAt: string;
}

/** Customer-facing 'my tickets' row (one conversation). */
export interface ApiConversationTicket {
  id: string;
  status: ApiTicketStatus;
  summary: string;
  createdAt: string;
  updatedAt: string;
}

export interface ApiConversationTicketList {
  conversationId: string;
  total: number;
  items: ApiConversationTicket[];
}

export interface ApiTicketEvent {
  id: string;
  eventType: string;
  oldValue: string | null;
  newValue: string | null;
  actor: string;
  createdAt: string;
}

export interface ApiTicketDetail extends ApiTicketSummary {
  originalQuestion: string;
  messages: ApiMessage[];
  events: ApiTicketEvent[];
}

export interface ApiTicketCounts {
  OPEN: number;
  IN_PROGRESS: number;
  RESOLVED: number;
}

export interface ApiTicketPage {
  items: ApiTicketSummary[];
  total: number;
  limit: number;
  offset: number;
  /** Counts matching the search query, ignoring the status filter. */
  counts: ApiTicketCounts;
}

export type ApiFeedbackRating = "helpful" | "not_helpful";

export interface ApiFeedback {
  id: string;
  messageId: string;
  rating: ApiFeedbackRating;
  reason: string | null;
  createdAt: string;
}

export type ApiDocumentStatus = "PENDING" | "PROCESSING" | "READY" | "FAILED";
export type ApiSourceType = "markdown" | "text";
/** Only "approved" enters normal retrieval; "challenge_fixture" is the
 *  labeled conflicting-evidence material (Phase 7 retrieval filtering). */
export type ApiKnowledgeStatus = "approved" | "challenge_fixture" | "archived";

/** One retrievable piece of a document, with its section provenance. */
export interface ApiChunk {
  id: string;
  chunkIndex: number;
  sectionId: string;
  sectionTitle: string;
  content: string;
  charCount: number;
  pipelineVersion: string;
  createdAt: string;
}

export interface ApiDocument {
  id: string;
  title: string;
  source: string | null;
  sourceType: ApiSourceType;
  knowledgeStatus: ApiKnowledgeStatus;
  status: ApiDocumentStatus;
  failureReason: string | null;
  contentHash: string | null;
  chunkCount: number;
  processedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ApiDocumentDetail extends ApiDocument {
  content: string;
  chunks: ApiChunk[];
}

export interface ApiDocumentCreate {
  title: string;
  content: string;
  source?: string;
  sourceType?: ApiSourceType;
  knowledgeStatus?: ApiKnowledgeStatus;
}

export interface ApiHealth {
  status: string;
  environment: string;
  /** Which AI providers are attached (Phase 10+ mode awareness). */
  llm_provider?: string;
  embedding_provider?: string;
  /** "offline_demo" | "live" | "partial" — drives the mode banner. */
  mode?: string;
}

/* ------------------------------------------------------------------ */
/* Provider settings (staff dialog) — keys are submitted once and      */
/* stored server-side; responses carry booleans + masked previews only */
/* ------------------------------------------------------------------ */

export interface ApiProviderSettings {
  environment: string;
  /** Configured providers: "live" = real NVIDIA; "test" = the deterministic
   *  test providers (only reachable when ENVIRONMENT=testing). */
  providerMode: "live" | "demo";
  embeddingProvider: string;
  llmProvider: string;
  embeddingModel: string;
  llmModel: string;
  embeddingKeyConfigured: boolean;
  llmKeyConfigured: boolean;
  embeddingKeyMasked: string | null;
  llmKeyMasked: string | null;
  modeNote: string;
}

export interface ApiProviderKeysUpdate {
  embeddingApiKey?: string;
  nvidiaApiKey?: string;
}

export interface ApiProviderVerifyRequest {
  embeddingApiKey?: string;
  nvidiaApiKey?: string;
}

export interface ApiProviderVerifyItem {
  ok: boolean;
  error: string | null;
}

export interface ApiProviderVerify {
  embedding: ApiProviderVerifyItem | null;
  chat: ApiProviderVerifyItem | null;
}

/* ------------------------------------------------------------------ */
/* Staff authentication — register/login return the bearer token once; */
/* the client stores it (lib/staff/session) and every request attaches */
/* it as Authorization: Bearer until sign-out or a 401.                */
/* ------------------------------------------------------------------ */

export interface ApiStaffUser {
  id: string;
  name: string;
  email: string;
  createdAt: string;
  lastLoginAt: string | null;
}

export interface ApiAuthSession {
  token: string;
  expiresAt: string;
  user: ApiStaffUser;
}

export interface ApiAuthStatus {
  /** False → first run: the workspace opens on the create-account screen. */
  hasStaffUser: boolean;
}

export interface ApiAuthRegister {
  name: string;
  email: string;
  password: string;
}

export interface ApiAuthLogin {
  email: string;
  password: string;
}

/* ------------------------------------------------------------------ */
/* Status mapping helpers (API canonical ↔ staff UI contract)          */
/* ------------------------------------------------------------------ */

const UI_TO_API_STATUS: Record<UiTicketStatus, ApiTicketStatus> = {
  open: "OPEN",
  in_progress: "IN_PROGRESS",
  resolved: "RESOLVED",
};

const API_TO_UI_STATUS: Record<ApiTicketStatus, UiTicketStatus> = {
  OPEN: "open",
  IN_PROGRESS: "in_progress",
  RESOLVED: "resolved",
};

export function toApiStatus(status: UiTicketStatus): ApiTicketStatus {
  return UI_TO_API_STATUS[status];
}

export function toUiStatus(status: ApiTicketStatus): UiTicketStatus {
  return API_TO_UI_STATUS[status];
}

/* ------------------------------------------------------------------ */
/* Transport                                                           */
/* ------------------------------------------------------------------ */

async function request<T>(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = init.method ?? "GET";
  const token = getToken();
  const headers: Record<string, string> | undefined =
    init.body === undefined
      ? token
        ? { Authorization: `Bearer ${token}` }
        : undefined
      : {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        };
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch (error) {
    // A user-initiated cancel (Esc / Stop) must stay distinguishable from
    // a network failure: rethrow the abort so the chat UI can show its
    // calm "cancelled" state instead of a scary connection error.
    if (init.signal?.aborted) throw error;
    // Network/CORS failure — never surface low-level details to the UI.
    throw new ApiError("Could not reach the support service.", {
      code: "NETWORK_ERROR",
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Non-JSON body (e.g. proxy error page).
  }

  if (!response.ok) {
    const envelope = payload as Partial<ErrorEnvelope> | null;
    const error = envelope?.error;
    throw new ApiError(error?.message ?? "The request could not be completed.", {
      status: response.status,
      code: error?.code ?? "UNKNOWN_ERROR",
      details: error?.details,
      requestId: error?.request_id ?? response.headers.get("X-Request-ID"),
    });
  }

  return payload as T;
}

/* ------------------------------------------------------------------ */
/* Endpoints                                                           */
/* ------------------------------------------------------------------ */

export const api = {
  health: (): Promise<ApiHealth> => request<ApiHealth>("/health"),

  auth: {
    /** GET /api/v1/auth/status — first-run probe (create vs. sign in). */
    status: (): Promise<ApiAuthStatus> => request<ApiAuthStatus>("/api/v1/auth/status"),

    /** POST /api/v1/auth/register — create the staff account + sign in.
     *  409 — the email is already registered. */
    register: (payload: ApiAuthRegister): Promise<ApiAuthSession> =>
      request<ApiAuthSession>("/api/v1/auth/register", { method: "POST", body: payload }),

    /** POST /api/v1/auth/login — 401 for unknown email OR wrong password
     *  (identical message; the API never reveals which accounts exist). */
    login: (payload: ApiAuthLogin): Promise<ApiAuthSession> =>
      request<ApiAuthSession>("/api/v1/auth/login", { method: "POST", body: payload }),

    /** GET /api/v1/auth/me — 401 when the stored token is gone/expired. */
    me: (): Promise<ApiStaffUser> => request<ApiStaffUser>("/api/v1/auth/me"),

    /** POST /api/v1/auth/logout — invalidates the token server-side. */
    logout: (): Promise<void> => request<void>("/api/v1/auth/logout", { method: "POST" }),
  },

  providers: {
    /** GET /api/v1/admin/provider-settings — booleans + masks, never keys. */
    get: (): Promise<ApiProviderSettings> =>
      request<ApiProviderSettings>("/api/v1/admin/provider-settings"),

    /** PUT /api/v1/admin/provider-settings/mode — local Demo/Live toggle. */
    setMode: (mode: "demo" | "live"): Promise<ApiProviderSettings> =>
      request<ApiProviderSettings>("/api/v1/admin/provider-settings/mode", {
        method: "PUT",
        body: { mode },
      }),

    /** PUT /api/v1/admin/provider-settings/keys — persist to backend/.env.
     *  Only the keys provided are changed; omitted fields are untouched. */
    saveKeys: (payload: ApiProviderKeysUpdate): Promise<ApiProviderSettings> =>
      request<ApiProviderSettings>("/api/v1/admin/provider-settings/keys", {
        method: "PUT",
        body: payload,
      }),

    /** POST /api/v1/admin/provider-settings/verify — one real provider call
     *  per submitted key; a wrong key is `ok: false`, not a fake success. */
    verify: (payload: ApiProviderVerifyRequest): Promise<ApiProviderVerify> =>
      request<ApiProviderVerify>("/api/v1/admin/provider-settings/verify", {
        method: "POST",
        body: payload,
      }),
  },

  chat: {
    /** POST /api/v1/chat/sessions — start a conversation. */
    createSession: (): Promise<ApiChatSession> =>
      request<ApiChatSession>("/api/v1/chat/sessions", {
        method: "POST",
        body: {},
      }),

    /** POST /api/v1/chat/sessions/{id}/messages — one customer turn.
     *  `clientRequestId` makes the turn idempotent; retries reuse the same
     *  id so a completed turn is replayed instead of duplicated.
     *  `signal` lets the caller cancel the WAIT (Esc/Stop) — the backend
     *  may still finish and persist the turn, which a retry then replays. */
    postMessage: (
      conversationId: string,
      content: string,
      clientRequestId?: string,
      signal?: AbortSignal,
    ): Promise<ApiChatTurn> =>
      request<ApiChatTurn>(
        `/api/v1/chat/sessions/${encodeURIComponent(conversationId)}/messages`,
        {
          method: "POST",
          body:
            clientRequestId === undefined
              ? { content }
              : { content, clientRequestId },
          signal,
        },
      ),

    /** GET /api/v1/chat/sessions/{id}/messages — reload transcript. */
    getMessages: (conversationId: string): Promise<ApiChatHistory> =>
      request<ApiChatHistory>(
        `/api/v1/chat/sessions/${encodeURIComponent(conversationId)}/messages`,
      ),
  },

  tickets: {
    /** POST /api/v1/conversations/{id}/escalations (409 = duplicate open ticket). */
    createEscalation: (
      conversationId: string,
      payload: ApiEscalationCreate,
    ): Promise<ApiTicketDetail> =>
      request<ApiTicketDetail>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/escalations`,
        { method: "POST", body: payload },
      ),

    /** GET /api/v1/admin/escalations — staff queue, newest first. */
    list: (params: {
      status?: ApiTicketStatus;
      q?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<ApiTicketPage> => {
      const query = new URLSearchParams();
      if (params.status) query.set("status", params.status);
      if (params.q) query.set("q", params.q);
      if (params.limit !== undefined) query.set("limit", String(params.limit));
      if (params.offset !== undefined) query.set("offset", String(params.offset));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<ApiTicketPage>(`/api/v1/admin/escalations${suffix}`);
    },

    /** GET /api/v1/conversations/{id}/escalations — every ticket raised
     *  from this conversation, newest first (customer 'my tickets'). */
    listForConversation: (conversationId: string): Promise<ApiConversationTicketList> =>
      request<ApiConversationTicketList>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/escalations`,
      ),

    /** GET /api/v1/admin/escalations/{id} — detail with transcript + events. */
    get: (ticketId: string): Promise<ApiTicketDetail> =>
      request<ApiTicketDetail>(
        `/api/v1/admin/escalations/${encodeURIComponent(ticketId)}`,
      ),

    /** PATCH /api/v1/admin/escalations/{id}/status (409 = stale status).
     *  The staff client always sends `expectedStatus` so a concurrent update
     *  cannot be silently overwritten. */
    setStatus: (
      ticketId: string,
      status: ApiTicketStatus,
      actor = "staff",
      expectedStatus?: ApiTicketStatus,
    ): Promise<ApiTicketDetail> =>
      request<ApiTicketDetail>(
        `/api/v1/admin/escalations/${encodeURIComponent(ticketId)}/status`,
        {
          method: "PATCH",
          body:
            expectedStatus === undefined
              ? { status, actor }
              : { status, actor, expectedStatus },
        },
      ),
  },

  feedback: {
    /** POST /api/v1/messages/{id}/feedback (409 = already recorded). */
    create: (
      messageId: string,
      rating: ApiFeedbackRating,
      reason?: string,
    ): Promise<ApiFeedback> =>
      request<ApiFeedback>(
        `/api/v1/messages/${encodeURIComponent(messageId)}/feedback`,
        { method: "POST", body: { rating, reason: reason ?? null } },
      ),
  },

  documents: {
    /** GET /api/v1/documents — docs + honest processing status + chunk counts. */
    list: (): Promise<ApiDocument[]> => request<ApiDocument[]>("/api/v1/documents"),

    /** GET /api/v1/documents/{id} — stored content + chunks with provenance. */
    get: (documentId: string): Promise<ApiDocumentDetail> =>
      request<ApiDocumentDetail>(
        `/api/v1/documents/${encodeURIComponent(documentId)}`,
      ),

    /** POST /api/v1/documents — synchronous ingestion; resolves READY or throws
     *  ApiError (409 duplicate content, 422 invalid/failed processing). */
    create: (payload: ApiDocumentCreate): Promise<ApiDocumentDetail> =>
      request<ApiDocumentDetail>("/api/v1/documents", {
        method: "POST",
        body: payload,
      }),

    /** POST /api/v1/documents/{id}/reprocess — re-run the pipeline over the
     *  stored content, replacing chunks (historical citations preserved). */
    reprocess: (documentId: string): Promise<ApiDocumentDetail> =>
      request<ApiDocumentDetail>(
        `/api/v1/documents/${encodeURIComponent(documentId)}/reprocess`,
        { method: "POST" },
      ),
  },
};
