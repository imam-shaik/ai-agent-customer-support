import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface NavItem {
  label: string;
  href: string;
  icon?: ReactNode;
  /** Small trailing count (queue depth, pending docs). */
  badge?: string | number;
  active?: boolean;
  disabled?: boolean;
}

interface SidebarProps {
  items: NavItem[];
  /** Pinned bottom section (status, version, account). */
  footer?: ReactNode;
  ariaLabel?: string;
  className?: string;
}

/**
 * Workspace rail — sticky under the top bar, desktop only.
 * The same items feed <MobileNavigation>.
 */
export function Sidebar({ items, footer, ariaLabel = "Workspace", className }: SidebarProps) {
  return (
    <aside
      className={cn(
        "sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-56 shrink-0 flex-col border-r border-line bg-surface-1 md:flex",
        className
      )}
    >
      <nav aria-label={ariaLabel} className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {items.map((item) => {
          const classes = cn(
            "flex h-9 items-center gap-2.5 rounded-control border px-3 text-sm font-medium transition-colors duration-fast",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-0",
            item.active
              ? "border-line bg-surface-3 text-ink"
              : "border-transparent text-ink-secondary hover:bg-surface-2 hover:text-ink",
            item.disabled && "pointer-events-none opacity-45"
          );
          const content = (
            <>
              {item.icon && (
                <span aria-hidden="true" className="shrink-0 [&_svg]:size-4">
                  {item.icon}
                </span>
              )}
              <span className="truncate">{item.label}</span>
              {item.badge !== undefined && (
                <span className="ml-auto rounded-full border border-line bg-surface-2 px-1.5 py-px text-[11px] font-medium text-ink-secondary">
                  {item.badge}
                </span>
              )}
            </>
          );

          if (item.disabled) {
            return (
              <span key={item.href} aria-disabled="true" className={classes}>
                {content}
              </span>
            );
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={item.active ? "page" : undefined}
              className={classes}
            >
              {content}
            </Link>
          );
        })}
      </nav>
      {footer && <div className="border-t border-line p-3">{footer}</div>}
    </aside>
  );
}
