/**
 * Presentational loading copy for the customer chat.
 *
 * The real chat turn is one synchronous HTTP request — the browser
 * receives no backend stage events, so the UI deliberately shows NO
 * stage labels (no "Searching…"/"Checking…" claims). The skeleton
 * communicates "an answer is being prepared" and nothing more.
 */

export const THINKING_HEADING = "Vilasat AI is preparing an answer";
export const THINKING_DETAIL =
  "Answers come only from approved documentation — this takes a few moments.";
