"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "neutral" | "success" | "danger" | "info";

interface ToastOptions {
  title: string;
  description?: string;
  tone?: ToastTone;
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastOptions {
  id: number;
  tone: ToastTone;
}

interface ToastContextValue {
  toast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_ICON: Record<ToastTone, ReactNode> = {
  neutral: <Info className="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden="true" />,
  info: <Info className="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />,
  success: (
    <CheckCircle className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
  ),
  danger: (
    <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
  ),
};

const TONE_BAR: Record<ToastTone, string> = {
  neutral: "border-l-ink-muted",
  info: "border-l-info",
  success: "border-l-success",
  danger: "border-l-danger",
};

interface ToastProviderProps {
  children: ReactNode;
  /** Time on screen before auto-dismiss. */
  duration?: number;
}

/**
 * Toast queue + viewport. Use for confirmations that shouldn't interrupt
 * (feedback recorded, status changed) — not for errors that need action.
 *
 *   const { toast } = useToast();
 *   toast({ title: "Feedback recorded", tone: "success" });
 */
export function ToastProvider({ children, duration = 5000 }: ToastProviderProps) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((options: ToastOptions) => {
    setItems((prev) => [...prev, { ...options, id: Date.now() + Math.random(), tone: options.tone ?? "neutral" }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider duration={duration} swipeDirection="right">
        {children}
        {items.map((item) => (
          <ToastPrimitive.Root
            key={item.id}
            type="background"
            onOpenChange={(open) => !open && dismiss(item.id)}
            className={cn(
              "group pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden",
              "rounded-md border border-l-2 border-line bg-surface-3 p-3.5 shadow-overlay",
              "data-[state=open]:animate-toast-in data-[state=closed]:animate-toast-out",
              TONE_BAR[item.tone]
            )}
          >
            {TONE_ICON[item.tone]}
            <div className="min-w-0 flex-1">
              <ToastPrimitive.Title className="text-sm font-medium text-ink">
                {item.title}
              </ToastPrimitive.Title>
              {item.description && (
                <ToastPrimitive.Description className="mt-0.5 text-xs leading-relaxed text-ink-secondary">
                  {item.description}
                </ToastPrimitive.Description>
              )}
            </div>
            {item.action && (
              <ToastPrimitive.Action
                altText={item.action.label}
                onClick={item.action.onClick}
                className="shrink-0 rounded-control border border-line bg-surface-2 px-2 py-1 text-xs font-medium text-ink transition-colors duration-fast hover:bg-surface-3 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
              >
                {item.action.label}
              </ToastPrimitive.Action>
            )}
            <ToastPrimitive.Close
              aria-label="Dismiss notification"
              className="shrink-0 rounded-control p-1 text-ink-muted transition-colors duration-fast hover:text-ink focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
            >
              <X className="size-3.5" aria-hidden="true" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 outline-hidden" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

/** Raise a toast from anywhere below the provider. */
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return context;
}
