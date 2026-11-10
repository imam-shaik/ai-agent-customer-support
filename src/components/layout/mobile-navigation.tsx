"use client";

import Link from "next/link";
import { Drawer } from "@/components/ui/drawer";
import type { NavItem } from "./sidebar";
import { cn } from "@/lib/utils";

interface MobileNavigationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: NavItem[];
  title?: string;
}

/** Slide-in navigation for small screens; shares items with <Sidebar>. */
export function MobileNavigation({
  open,
  onOpenChange,
  items,
  title = "Navigation",
}: MobileNavigationProps) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange} title={title} side="left">
      <nav aria-label="Mobile navigation" className="-mx-5 -my-5 flex flex-col gap-0.5 px-3 py-3">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => onOpenChange(false)}
            aria-current={item.active ? "page" : undefined}
            className={cn(
              "flex h-10 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors duration-fast",
              "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
              item.active
                ? "bg-surface-3 text-ink"
                : "text-ink-secondary hover:bg-surface-2 hover:text-ink",
              item.disabled && "pointer-events-none opacity-45"
            )}
          >
            {item.icon && (
              <span aria-hidden="true" className="[&_svg]:size-4">
                {item.icon}
              </span>
            )}
            <span>{item.label}</span>
            {item.badge !== undefined && (
              <span className="ml-auto rounded-full border border-line bg-surface-2 px-1.5 py-px text-[11px] font-medium text-ink-secondary">
                {item.badge}
              </span>
            )}
          </Link>
        ))}
      </nav>
    </Drawer>
  );
}
