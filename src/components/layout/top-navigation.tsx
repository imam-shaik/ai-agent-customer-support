"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import type { ReactNode } from "react";
import { Logo } from "@/components/brand/Logo";
import { Avatar } from "@/components/ui/avatar";
import { IconButton } from "@/components/ui/icon-button";
import { ProviderControls } from "@/components/domain/settings/provider-controls";
import { ThemeToggle } from "./theme-toggle";
import type { NavItem } from "./sidebar";
import { cn } from "@/lib/utils";

interface TopNavigationProps {
  /** Primary links (desktop only). */
  navItems?: NavItem[];
  user?: { name: string; src?: string };
  /** Optional extra right-aligned actions (rendered after provider controls). */
  actions?: ReactNode;
  onOpenMobileNav?: () => void;
}

/** Sticky global header: brand, primary links, provider controls, account. */
export function TopNavigation({
  navItems = [],
  user,
  actions,
  onOpenMobileNav,
}: TopNavigationProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-3 px-4 md:px-6">
        <Link
          href="/"
          aria-label="Vilasat AI Support Intelligence — home"
          className="shrink-0 rounded-control focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          <Logo showProduct />
        </Link>

        <span
          title="Northstar Desk is a fictional demo tenant. All documents and customer information are synthetic."
          className="hidden items-center gap-1 rounded-full border border-warning-border bg-warning-soft px-2 py-0.5 text-[10px] font-medium text-warning-ink sm:inline-flex"
        >
          Demo · synthetic data
        </span>

        {navItems.length > 0 && (
          <nav aria-label="Primary" className="ml-4 hidden items-center gap-1 lg:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={item.active ? "page" : undefined}
                className={cn(
                  "rounded-control px-3 py-1.5 text-sm font-medium transition-colors duration-fast",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                  item.active
                    ? "bg-surface-2 text-ink"
                    : "text-ink-secondary hover:bg-surface-1 hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2">
          <ProviderControls />
          <ThemeToggle />
          {actions}
          {user && (
            <span className="flex items-center gap-2">
              <Avatar name={user.name} src={user.src} />
              <span className="hidden text-sm text-ink-secondary md:inline">{user.name}</span>
            </span>
          )}
          {onOpenMobileNav && (
            <span className="lg:hidden">
              <IconButton label="Open navigation" onClick={onOpenMobileNav}>
                <Menu />
              </IconButton>
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
