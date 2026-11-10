"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const SIZES = {
  xs: "size-5 text-[9px]",
  sm: "size-7 text-[11px]",
  md: "size-9 text-xs",
} as const;

interface AvatarProps {
  /** Full name — initials are derived from it. */
  name: string;
  /** Optional image; falls back to initials if it fails to load. */
  src?: string;
  size?: keyof typeof SIZES;
  className?: string;
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Person or entity avatar: image with deterministic initials fallback. */
export function Avatar({ name, src, size = "sm", className }: AvatarProps) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);

  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full border border-line bg-surface-2 font-medium text-ink-secondary",
        SIZES[size],
        className
      )}
    >
      {src && !failed ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="size-full object-cover"
        />
      ) : (
        initialsOf(name)
      )}
    </span>
  );
}
