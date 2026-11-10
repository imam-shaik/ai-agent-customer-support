"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  EASE_STANDARD,
  MOTION_DURATION,
  RISE_OFFSET,
  staggerContainer,
  viewportOnce,
} from "@/lib/motion";

interface StaggerProps {
  children: ReactNode;
  className?: string;
  /** Delay before the first child animates. */
  delay?: number;
  /** Delay between children. */
  stagger?: number;
}

/**
 * Staggered list entrance. Children animate as they enter the viewport,
 * once only. Pair with <StaggerItem>.
 *
 *   <Stagger className="grid gap-4">
 *     <StaggerItem>…</StaggerItem>
 *   </Stagger>
 */
export function Stagger({ children, className, delay = 0, stagger = 0.05 }: StaggerProps) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      variants={{
        ...staggerContainer,
        visible: {
          ...(staggerContainer.visible as object),
          transition: { staggerChildren: stagger, delayChildren: delay },
        },
      }}
    >
      {children}
    </motion.div>
  );
}

interface StaggerItemProps {
  children: ReactNode;
  className?: string;
}

export function StaggerItem({ children, className }: StaggerItemProps) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: RISE_OFFSET },
        visible: {
          opacity: 1,
          y: 0,
          transition: { duration: MOTION_DURATION.base, ease: EASE_STANDARD },
        },
      }}
    >
      {children}
    </motion.div>
  );
}
