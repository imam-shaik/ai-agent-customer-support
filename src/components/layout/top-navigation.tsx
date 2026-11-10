"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Logo } from "@/components/brand/Logo";
import { Avatar } from "@/components/ui/avatar";
import { IconButton } from "@/components/ui/icon-button";
import {
  PROVIDER_MODE_EVENT,
  ProviderControls,
} from "@/components/domain/settings/provider-controls";
import { api, ApiError } from "@/lib/api/client";
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

type TenantMode = "demo" | "live" | "partial" | "offline";

const TENANT_BADGE: Record<
  TenantMode,
  { text: string; title: string; tone: string }
> = {
  demo: {
    text: "Demo · synthetic data",
    title:
      "Demo mode — deterministic local answers, no external API calls. Northstar Desk is a fictional tenant; all documents and customer information are synthetic.",
    tone: "border-warning-border bg-warning-soft text-warning-ink",
  },
  live: {
    text: "Live · synthetic data",
    title:
      "Answers come from the live configured providers. Northstar Desk is a fictional demo tenant — all documents and customer information are synthetic.",
    tone: "border-success-border bg-success-soft text-success-ink",
  },
  partial: {
    text: "Live · setup incomplete",
    title:
      "Live providers are selected but an API key is missing — see the banner below. All tenant data is synthetic.",
    tone: "border-warning-border bg-warning-soft text-warning-ink",
  },
  offline: {
    text: "Service offline",
    title: "Can't reach the support service right now. All tenant data is synthetic.",
    tone: "border-danger-border bg-danger-soft text-danger-ink",
  },
};

/**
 * Mode-aware tenant pill next to the brand. Uses the same source of truth
 * as the mode banner (backend health mode + provider-mode change events),
 * so the header never says "Demo" while the Live providers are attached.
 * Occupies its space while the first probe is in flight (no layout shift).
 */
function TenantBadge() {
  const [mode, setMode] = useState<TenantMode | null>(null);

  useEffect(() => {
    let alive = true;

    async function check() {
      try {
        const health = await api.health();
        if (!alive) return;
        const reported = health.mode;
        setMode(
          reported === "offline_demo"
            ? "demo"
            : reported === "partial"
              ? "partial"
              : "live",
        );
      } catch (error) {
        if (!alive) return;
        setMode(
          error instanceof ApiError && error.status === 0 ? "offline" : "live",
        );
      }
    }

    void check();
    const timer = window.setInterval(() => void check(), 60_000);
    window.addEventListener(PROVIDER_MODE_EVENT, check);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(PROVIDER_MODE_EVENT, check);
    };
  }, []);

  const badge = mode === null ? null : TENANT_BADGE[mode];

  return (
    <span
      title={badge?.title ?? "Checking AI provider mode…"}
      aria-label={badge?.text ?? "Checking AI provider mode"}
      className={cn(
        "hidden items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium sm:inline-flex",
        badge ? badge.tone : "invisible border-transparent",
      )}
    >
      {badge?.text ?? "…"}
    </span>
  );
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

        <TenantBadge />

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
