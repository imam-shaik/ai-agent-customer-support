/**
 * Staff ticket presentation vocabulary.
 *
 * Real ticket data comes from the Phase 5 API; this module intentionally
 * contains no demo tickets or client-side filtering.
 */

export type TicketStatus = "open" | "in_progress" | "resolved";

export const STATUS_OPTIONS: Array<{ value: TicketStatus; label: string }> = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
];

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
};

/** Demo identity until staff authentication exists (production gate). */
export const STAFF_MEMBER = "Maya Chen";
