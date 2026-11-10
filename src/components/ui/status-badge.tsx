import { cn } from "@/lib/utils";

export type TicketStatus = "open" | "in_progress" | "resolved";
export type IndexStatus = "queued" | "indexing" | "indexed" | "failed";
export type AnyStatus = TicketStatus | IndexStatus;

const STATUS_CONFIG: Record<AnyStatus, { label: string; dot: string }> = {
  open: { label: "Open", dot: "bg-info" },
  in_progress: { label: "In progress", dot: "bg-warning" },
  resolved: { label: "Resolved", dot: "bg-success" },
  queued: { label: "Queued", dot: "bg-ink-muted" },
  indexing: { label: "Indexing", dot: "bg-info" },
  indexed: { label: "Indexed", dot: "bg-success" },
  failed: { label: "Failed", dot: "bg-danger" },
};

interface StatusBadgeProps {
  status: AnyStatus;
  /** One soft pulse — mark a status transition as it happens. */
  pulse?: boolean;
  className?: string;
}

/**
 * Status indicator: dot + text label (never color alone).
 * One shared vocabulary for tickets and knowledge indexing.
 */
export function StatusBadge({ status, pulse = false, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-ink-secondary",
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          config.dot,
          pulse && "animate-pulse-once"
        )}
      />
      {config.label}
    </span>
  );
}
