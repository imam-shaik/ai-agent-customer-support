import type { Variants } from "framer-motion";

/**
 * Motion tokens (mirrors the CSS token layer in globals.css).
 * Keep both in sync — components import from here for JS-driven motion.
 */

/** Standard easing: quick-out, gentle settle. */
export const EASE_STANDARD: [number, number, number, number] = [0.2, 0, 0, 1];

export const MOTION_DURATION = {
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
} as const;

/** Entrance travel distance — subtle, never floaty. */
export const RISE_OFFSET = 10;

export const fadeVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

export const riseVariants: Variants = {
  hidden: { opacity: 0, y: RISE_OFFSET },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: MOTION_DURATION.base, ease: EASE_STANDARD },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.05, delayChildren: 0.04 },
  },
};

/** Shared viewport config: animate once when entering the viewport. */
export const viewportOnce = { once: true, margin: "-40px" } as const;
