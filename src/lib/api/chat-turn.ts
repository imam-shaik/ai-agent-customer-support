/**
 * Customer chat seam — the real replacement for the Phase 3 mock agent.
 *
 * Components never call `fetch`; this module is the only chat call site
 * and delegates transport to `api`. It also owns the per-turn idempotency
 * key: the same id is sent again for every retry of the same submission.
 */

import {
  api,
  ApiError,
  type ApiChatHistory,
  type ApiChatTurn,
  type ApiFeedbackRating,
} from "./client";

/**
 * Stable UUID v4 for one customer submission.
 *
 * `crypto.randomUUID` is unavailable in some non-secure contexts, so fall
 * back to `getRandomValues` (still a real UUID the backend accepts).
 */
export function makeClientRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();

  const bytes = new Uint8Array(16);
  if (cryptoApi?.getRandomValues) {
    cryptoApi.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

export function createSession(): Promise<string> {
  return api.chat.createSession().then((session) => session.conversationId);
}

export function sendTurn(
  conversationId: string,
  content: string,
  clientRequestId?: string,
  signal?: AbortSignal,
): Promise<ApiChatTurn> {
  return api.chat.postMessage(conversationId, content, clientRequestId, signal);
}

export function loadConversation(conversationId: string): Promise<ApiChatHistory> {
  return api.chat.getMessages(conversationId);
}

export function saveFeedback(
  messageId: string,
  rating: ApiFeedbackRating,
  reason?: string,
): Promise<void> {
  return api.feedback.create(messageId, rating, reason).then(() => undefined);
}

/** A retry only makes sense for transport/provider failures (and a
 *  stale conversation, where retry starts a fresh session). */
export function isRetryableError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return (
    error.code === "NETWORK_ERROR" ||
    error.status === 404 ||
    error.status === 502 ||
    error.status === 503 ||
    error.status >= 500
  );
}
