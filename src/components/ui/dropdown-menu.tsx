"use client";

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

/** Root + Trigger re-export — pair with <DropdownMenuTrigger asChild>. */
const DropdownMenu = DropdownMenuPrimitive.Root;
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
const DropdownMenuGroup = DropdownMenuPrimitive.Group;

interface DropdownMenuContentProps
  extends ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content> {}

function DropdownMenuContent({
  sideOffset = 6,
  align = "end",
  className,
  ...props
}: DropdownMenuContentProps) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        sideOffset={sideOffset}
        align={align}
        className={cn(
          "z-50 min-w-[10rem] overflow-hidden rounded-md border border-line bg-surface-2 p-1 shadow-pop",
          "animate-menu-in data-[state=closed]:animate-menu-out",
          className
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

interface DropdownMenuItemProps extends ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> {}

function DropdownMenuItem({ className, ...props }: DropdownMenuItemProps) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        "relative flex cursor-pointer select-none items-center gap-2 rounded-control px-2.5 py-2 text-sm text-ink-secondary outline-none transition-colors duration-fast",
        "data-[highlighted]:bg-surface-3 data-[highlighted]:text-ink",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className
      )}
      {...props}
    />
  );
}

function DropdownMenuLabel({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label>) {
  return (
    <DropdownMenuPrimitive.Label
      className={cn("px-2.5 py-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted", className)}
      {...props}
    />
  );
}

function DropdownMenuSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator
      className={cn("-mx-1 my-1 h-px bg-line", className)}
      {...props}
    />
  );
}

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuGroup,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
};
