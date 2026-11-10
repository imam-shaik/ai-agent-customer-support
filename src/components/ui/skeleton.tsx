import { cn } from "@/lib/utils";

interface SkeletonProps {
  /** Tailwind size classes, e.g. "h-4 w-40" or "aspect-video". */
  className?: string;
}

/**
 * Loading placeholder with shimmer. Always aria-hidden — pair with a
 * polite live-region announcement where the wait matters.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("skeleton block h-4 w-full rounded-control", className)}
    />
  );
}
