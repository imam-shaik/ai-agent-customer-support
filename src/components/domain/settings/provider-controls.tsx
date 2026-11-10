"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { api, ApiError, type ApiProviderSettings } from "@/lib/api/client";
import { ProviderSettingsDialog } from "./provider-settings-dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Broadcast so the mode banner can refresh without a page reload. */
export const PROVIDER_MODE_EVENT = "vilasat:provider-mode-changed";

/**
 * Header provider controls — the local Demo/Live switch, provider status,
 * and the API-key dialog.
 *
 * Demo runs deterministic local retrieval + generation over the same
 * stored documents. It never touches the live pgvector index or the
 * saved keys; switching back to Live restores the configured NVIDIA
 * providers immediately. Demo is refused by the backend in production,
 * so the control is hidden there.
 */
export function ProviderControls() {
  const [status, setStatus] = useState<ApiProviderSettings | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.providers.get());
    } catch {
      // Header control stays quiet on probe failure; the mode banner
      // already surfaces connectivity problems honestly.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const demo = status?.providerMode === "demo";
  const production = status?.environment === "production";
  const keysMissing =
    status !== null && (!status.embeddingKeyConfigured || !status.llmKeyConfigured);

  const switchMode = useCallback(
    async (mode: "demo" | "live") => {
      if (switching || status?.providerMode === mode) return;
      setSwitching(true);
      setToggleError(null);
      try {
        const next = await api.providers.setMode(mode);
        setStatus(next);
        window.dispatchEvent(new Event(PROVIDER_MODE_EVENT));
      } catch (error) {
        setToggleError(
          error instanceof ApiError
            ? error.message
            : "Could not switch modes. The previous mode is still active.",
        );
      } finally {
        setSwitching(false);
      }
    },
    [status?.providerMode, switching],
  );

  return (
    <div className="flex items-center gap-1.5">
      {status && !production && (
        <div
          role="group"
          aria-label="AI answer mode"
          className="flex items-center rounded-full border border-line bg-surface-2 p-0.5"
          title={
            demo
              ? "Demo: deterministic local answers, no network calls"
              : "Live: configured NVIDIA providers"
          }
        >
          <button
            type="button"
            aria-pressed={!demo}
            disabled={switching}
            onClick={() => void switchMode("live")}
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors duration-fast",
              "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
              !demo
                ? "bg-success-soft text-success-ink"
                : "text-ink-muted hover:text-ink",
            )}
          >
            Live
          </button>
          <button
            type="button"
            aria-pressed={demo}
            disabled={switching}
            onClick={() => void switchMode("demo")}
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors duration-fast",
              "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
              demo
                ? "bg-info-soft text-info-ink"
                : "text-ink-muted hover:text-ink",
            )}
          >
            Demo
          </button>
        </div>
      )}
      {production && (
        <span className="rounded-full border border-line bg-surface-2 px-2 py-1 font-mono text-[11px] text-ink-secondary">
          Live
        </span>
      )}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setDialogOpen(true)}
        aria-label="AI provider settings"
        title="Add or update the NVIDIA API keys (stored server-side)"
        className="gap-1.5"
      >
        <KeyRound aria-hidden="true" className="size-3.5" />
        <span className="hidden md:inline">API key</span>
        {status && keysMissing && (
          <span aria-hidden="true" className="size-1.5 rounded-full bg-warning" />
        )}
      </Button>
      <ProviderSettingsDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) void refresh();
        }}
      />
      {toggleError && (
        <span role="status" className="sr-only">
          {toggleError}
        </span>
      )}
    </div>
  );
}
