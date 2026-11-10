import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface KbdProps {
  children: ReactNode;
  className?: string;
}

/** Keyboard key hint — shortcuts like Enter / Shift+Enter. */
export function Kbd({ children, className }: KbdProps) {
  return (
    <kbd
      className={cn(
        "pointer-events-none inline-flex h-5 min-w-5 items-center justify-center rounded-[4px] border border-line bg-surface-2 px-1.5 font-mono text-[11px] font-medium text-ink-muted",
        className
      )}
    >
      {children}
    </kbd>
  );
}
