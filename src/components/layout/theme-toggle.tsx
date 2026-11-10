"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

type Theme = "dark" | "light";

const STORAGE_KEY = "vilasat.theme";

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "light" ? "#f2f3f7" : "#0d0e12");
}

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/**
 * Dark/light switch. Persists to localStorage and applies instantly via
 * the `data-theme` attribute consumed by the token overrides in
 * globals.css. Renders a stable placeholder until mounted so the server
 * and client never disagree on the icon (the boot script in layout.tsx
 * may already have applied the persisted theme).
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(currentTheme());
  }, []);

  function toggle() {
    const next: Theme = theme === "light" ? "dark" : "light";
    applyTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Persistence unavailable (private mode) — the choice still applies
      // for this page session.
    }
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={
        theme === "light" ? "Switch to dark theme" : "Switch to light theme"
      }
      title={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
      className={cn(
        "flex size-9 items-center justify-center rounded-control text-ink-secondary",
        "transition-colors duration-fast hover:bg-surface-2 hover:text-ink",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
        className,
      )}
    >
      {theme === null ? (
        <span aria-hidden="true" className="size-4" />
      ) : theme === "light" ? (
        <Moon aria-hidden="true" className="size-4" />
      ) : (
        <Sun aria-hidden="true" className="size-4" />
      )}
    </button>
  );
}
