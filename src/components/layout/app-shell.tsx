"use client";

import { useState, type ReactNode } from "react";
import { TopNavigation } from "./top-navigation";
import { Sidebar, type NavItem } from "./sidebar";
import { MobileNavigation } from "./mobile-navigation";

interface AppShellProps {
  /** Sidebar (and mobile) navigation items. */
  navItems: NavItem[];
  /** Optional distinct header links. */
  topNavItems?: NavItem[];
  user?: { name: string; src?: string };
  sidebarFooter?: ReactNode;
  children: ReactNode;
}

/**
 * Application frame: skip link → sticky top bar → sidebar + main →
 * mobile drawer. Wrap every workspace route in this.
 */
export function AppShell({
  navItems,
  topNavItems,
  user,
  sidebarFooter,
  children,
}: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-control focus:border focus:border-line focus:bg-surface-3 focus:px-3 focus:py-2 focus:text-sm focus:text-ink"
      >
        Skip to content
      </a>

      <TopNavigation
        navItems={topNavItems}
        user={user}
        onOpenMobileNav={() => setMobileNavOpen(true)}
      />

      <div className="mx-auto flex w-full max-w-[1440px] flex-1">
        <Sidebar items={navItems} footer={sidebarFooter} />
        <main id="main-content" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      <MobileNavigation
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
        items={navItems}
      />
    </div>
  );
}
