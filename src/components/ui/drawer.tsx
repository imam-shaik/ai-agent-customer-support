"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { IconButton } from "./icon-button";
import { cn } from "@/lib/utils";

const Dialog = DialogPrimitive.Root;

const SIDES = {
  left: "inset-y-0 left-0 h-full w-full max-w-[18rem] border-r animate-drawer-left-in data-[state=closed]:animate-drawer-left-out",
  right:
    "inset-y-0 right-0 h-full w-full max-w-md border-l animate-drawer-right-in data-[state=closed]:animate-drawer-right-out",
  bottom:
    "inset-x-0 bottom-0 max-h-[85vh] w-full rounded-t-sheet border-t animate-drawer-bottom-in data-[state=closed]:animate-drawer-bottom-out",
} as const;

interface DrawerProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Which edge the drawer slides from. */
  side?: keyof typeof SIDES;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * Edge-anchored panel for secondary flows (mobile nav, sources,
 * escalation step-by-step). Modal a11y semantics; slide + fade motion.
 */
export function Drawer({
  open,
  defaultOpen,
  onOpenChange,
  trigger,
  title,
  description,
  side = "right",
  footer,
  children,
  className,
}: DrawerProps) {
  return (
    <Dialog open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
      {trigger && <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 animate-overlay-in data-[state=closed]:animate-overlay-out" />
        <DialogPrimitive.Content
          className={cn(
            "fixed z-50 flex flex-col border-line bg-surface-1 shadow-overlay",
            SIDES[side],
            className
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <DialogPrimitive.Title className="font-display text-base font-semibold tracking-tight text-ink">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-sm text-ink-secondary">
                  {description}
                </DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">
                  {typeof title === "string" ? title : "Panel"}
                </DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close asChild>
              <IconButton label="Close panel" size="sm" className="-mr-1.5 -mt-1">
                <X />
              </IconButton>
            </DialogPrimitive.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 text-sm text-ink-secondary">
            {children}
          </div>

          {footer && (
            <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-2/40 px-5 py-4">
              {footer}
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </Dialog>
  );
}
