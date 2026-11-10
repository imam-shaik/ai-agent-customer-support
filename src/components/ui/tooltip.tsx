"use client";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Root + Trigger + Provider re-export — the provider lives in <Providers>. */
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;
const TooltipProvider = TooltipPrimitive.Provider;

interface TooltipContentProps extends ComponentPropsWithoutRef<typeof TooltipPrimitive.Content> {
  children: ReactNode;
}

/**
 * Short contextual hint on hover/focus. Provider lives in <Providers>.
 * Never contains information that isn't available elsewhere.
 */
function TooltipContent({
  side = "top",
  sideOffset = 6,
  className,
  children,
  ...props
}: TooltipContentProps) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        side={side}
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-control border border-line bg-surface-3 px-2.5 py-1.5",
          "text-xs font-medium leading-snug text-ink-secondary shadow-pop",
          "animate-tooltip-in data-[state=closed]:animate-tooltip-out",
          className
        )}
        {...props}
      >
        {children}
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
