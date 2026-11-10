"use client";

import { useEffect, useState } from "react";
import { Info, TriangleAlert, WifiOff } from "lucide-react";
import { api, ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Mode = "offline_demo" | "live" | "partial" | "unreachable" | "loading";

const BANNERS: Record<
  Exclude<Mode, "live">,
  { tone: "info" | "warning" | "danger"; icon: typeof Info; text: string }
> = {
  offline_demo: {
    tone: "info",
    icon: Info,
    text: "Demo mode — deterministic local answers over the synthetic Northstar Desk documents. No external API calls; your live keys and search index are untouched.",
  },
  partial: {
    tone: "warning",
    icon: TriangleAlert,
    text: "API configuration incomplete — some answers may be unavailable. Set EMBEDDING_API_KEY and NVIDIA_API_KEY in backend\\.env, then restart.",
  },
  unreachable: {
    tone: "danger",
    icon: WifiOff,
    text: "Can't reach the support service right now — your messages are kept locally and sent once it's back.",
  },
  loading: {
    tone: "info",
    icon: Info,
    text: "",
  },
};

/**
 * Provider-mode banner (design decision: surfaced at the top of both
 * workspaces). Shows when the backend reports demo/partial provider
 * configuration or is unreachable; stays silent when the real API is
 * attached (live) — once keys are configured the backend uses them
 * until the configuration changes.
 *
 * The mode is re-checked every 60s, so switching run.bat modes is
 * reflected without a rebuild.
 */
export function ModeBanner() {
  const [mode, setMode] = useState<Mode>("loading");

  useEffect(() => {
    let alive = true;

    async function check() {
      try {
        const health = await api.health();
        if (!alive) return;
        const reported = health.mode;
        setMode(
          reported === "offline_demo" || reported === "live" || reported === "partial"
            ? reported
            : "live", // older backend without mode field → treat as normal
        );
      } catch (error) {
        if (!alive) return;
        // Only surface a persistent outage after the first probe fails
        // with a network-level error (not a documented HTTP envelope).
        setMode(error instanceof ApiError && error.status === 0 ? "unreachable" : "live");
      }
    }

    void check();
    const timer = window.setInterval(() => void check(), 60_000);
    const onModeChange = () => void check();
    window.addEventListener("vilasat:provider-mode-changed", onModeChange);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("vilasat:provider-mode-changed", onModeChange);
    };
  }, []);

  if (mode === "live" || mode === "loading") {
    // Live stays quiet (silence = real providers attached); the first
    // probe holds its breath instead of flashing a banner.
    return null;
  }

  const banner = BANNERS[mode];
  if (!banner.text) return null;
  const Icon = banner.icon;

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-2.5 border-b px-4 py-2 text-xs leading-relaxed md:px-6",
        banner.tone === "info" && "border-info-border bg-info-soft text-info-ink",
        banner.tone === "warning" && "border-warning-border bg-warning-soft text-warning-ink",
        banner.tone === "danger" && "border-danger-border bg-danger-soft text-danger-ink",
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      <p className="min-w-0">{banner.text}</p>
    </div>
  );
}
