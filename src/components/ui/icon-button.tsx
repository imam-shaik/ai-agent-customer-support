"use client";

import type { ComponentPropsWithoutRef, ReactNode, Ref } from "react";
import { Button } from "./button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";
import { cn } from "@/lib/utils";

interface IconButtonProps {
  /** Required accessible name (also the tooltip text when enabled). */
  label: string;
  /** Wrap with a tooltip showing the label. */
  tooltip?: boolean;
  tone?: "default" | "subtle" | "danger";
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  onClick?: ComponentPropsWithoutRef<"button">["onClick"];
  ref?: Ref<HTMLButtonElement>;
  children: ReactNode;
}

/**
 * Icon-only button. The label is mandatory for screen readers;
 * tooltips are optional visual reinforcement.
 */
export function IconButton({
  label,
  tooltip = false,
  tone = "default",
  size = "md",
  className,
  disabled,
  onClick,
  ref,
  children,
}: IconButtonProps) {
  const variant = tone === "subtle" ? "secondary" : tone === "danger" ? "danger" : "ghost";

  const button = (
    <Button
      ref={ref}
      variant={variant}
      size={size === "sm" ? "icon-sm" : "icon"}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(tone === "default" && "text-ink-muted hover:text-ink", className)}
    >
      {children}
    </Button>
  );

  if (!tooltip) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
