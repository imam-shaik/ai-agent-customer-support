import { cn } from "@/lib/utils";

/**
 * Vilasat AI brand mark — an amber spark in a quiet rounded frame.
 * Presentational only (no link); parents wrap with <Link>.
 */

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className={cn("size-6 shrink-0", className)}
    >
      <rect
        x="0.75"
        y="0.75"
        width="18.5"
        height="18.5"
        rx="5.25"
        className="fill-accent-soft stroke-accent-border"
        strokeWidth="1.5"
      />
      <path
        d="M10 3.4C10.44 6.66 13.34 9.56 16.6 10C13.34 10.44 10.44 13.34 10 16.6C9.56 13.34 6.66 10.44 3.4 10C6.66 9.55 9.55 6.66 10 3.4Z"
        fill="var(--color-accent)"
      />
    </svg>
  );
}

interface LogoProps {
  /** Hide the wordmark (icon-only, used in tight spaces). */
  compact?: boolean;
  /** Show "Support Intelligence" after a divider (larger screens only). */
  showProduct?: boolean;
  className?: string;
}

export function Logo({ compact = false, showProduct = false, className }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      {!compact && (
        <span className="font-display text-[15px] font-semibold tracking-tight text-ink">
          Vilasat <span className="font-medium text-ink-muted">AI</span>
        </span>
      )}
      {showProduct && (
        <span
          aria-hidden="true"
          className="ml-1 hidden border-l border-line pl-3 font-sans text-xs font-medium tracking-wide text-ink-muted lg:inline"
        >
          Support Intelligence
        </span>
      )}
    </span>
  );
}
