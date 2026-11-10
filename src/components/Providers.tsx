"use client";

import type { ReactNode } from "react";
import { MotionConfig } from "framer-motion";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { EASE_STANDARD, MOTION_DURATION } from "@/lib/motion";

/**
 * Root client providers:
 * - MotionConfig: single motion default + honors prefers-reduced-motion
 * - TooltipProvider: shared tooltip timing
 * - ToastProvider: application toast queue
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionConfig
      reducedMotion="user"
      transition={{ duration: MOTION_DURATION.base, ease: EASE_STANDARD }}
    >
      <TooltipProvider delayDuration={300} skipDelayDuration={600}>
        <ToastProvider>{children}</ToastProvider>
      </TooltipProvider>
    </MotionConfig>
  );
}
