import { cn } from "@/lib/utils";

/**
 * Northstar Desk tenant identity — an original synthetic mark:
 * a four-point north star (distinct from Vilasat's curved spark).
 */

export function NorthstarMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className={cn("size-8 shrink-0", className)}
    >
      <rect
        x="0.75"
        y="0.75"
        width="18.5"
        height="18.5"
        rx="5.25"
        className="fill-info-soft stroke-info-border"
        strokeWidth="1.5"
      />
      <path
        d="M10 3L11.6 8.4L17 10L11.6 11.6L10 17L8.4 11.6L3 10L8.4 8.4L10 3Z"
        fill="var(--color-info)"
      />
    </svg>
  );
}

export function NorthstarLogo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <NorthstarMark />
      <span className="min-w-0">
        <span className="block font-display text-[15px] font-semibold tracking-tight text-ink">
          Northstar Desk
        </span>
        <span className="block text-[11px] font-medium tracking-wide text-ink-muted">
          Customer support workspace
        </span>
      </span>
    </span>
  );
}
