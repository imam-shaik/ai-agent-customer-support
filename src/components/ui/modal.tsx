"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { IconButton } from "./icon-button";
import { cn } from "@/lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;

const SIZES = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
} as const;

interface ModalProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Element that opens the modal (gets trigger behavior). */
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  size?: keyof typeof SIZES;
  showClose?: boolean;
  children: ReactNode;
  className?: string;
}

/**
 * Centered dialog for focused tasks (escalation details, confirmations).
 * Focus is trapped while open and restored to the trigger on close.
 */
export function Modal({
  open,
  defaultOpen,
  onOpenChange,
  trigger,
  title,
  description,
  footer,
  size = "md",
  showClose = true,
  children,
  className,
}: ModalProps) {
  return (
    <Dialog open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 animate-overlay-in data-[state=closed]:animate-overlay-out" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "overflow-hidden rounded-sheet border border-line bg-surface-1 p-6 shadow-overlay animate-dialog-in data-[state=closed]:animate-dialog-out",
            SIZES[size],
            className
          )}
        >
          <div className="flex shrink-0 items-start justify-between gap-4">
            <div className="min-w-0">
              <DialogPrimitive.Title className="font-display text-lg font-semibold tracking-tight text-ink">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1.5 text-sm leading-relaxed text-ink-secondary">
                  {description}
                </DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">
                  {typeof title === "string" ? title : "Dialog"}
                </DialogPrimitive.Description>
              )}
            </div>
            {showClose && (
              <DialogPrimitive.Close asChild>
                <IconButton label="Close dialog" size="sm" className="-mr-1.5 -mt-1">
                  <X />
                </IconButton>
              </DialogPrimitive.Close>
            )}
          </div>

          {/* Body scrolls when a dialog is taller than the viewport; the
              title and footer stay pinned and the panel stays centered
              (top/bottom margin of 1rem via the max-h cap). */}
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain text-sm text-ink-secondary">
            {children}
          </div>

          {footer && (
            <div className="mt-6 flex shrink-0 flex-wrap items-center justify-end gap-2">
              {footer}
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </Dialog>
  );
}
