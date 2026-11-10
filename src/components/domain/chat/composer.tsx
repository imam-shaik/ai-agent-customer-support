"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";

const MAX_LENGTH = 1000;
const MIN_LENGTH = 2;

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** Disabled while the agent is working. */
  busy?: boolean;
}

/**
 * Message composer: the primary interaction surface. Auto-growing
 * textarea in a shell whose material changes on focus (border + inner
 * ring + surface lift — no glow), Enter sends / Shift+Enter breaks,
 * counter appears near the limit, and the send button morphs to a live
 * pulse while the turn is in flight.
 */
export function Composer({ value, onChange, onSend, busy = false }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const trimmed = value.trim();
  const canSend = trimmed.length >= MIN_LENGTH && value.length <= MAX_LENGTH && !busy;
  const nearLimit = value.length > MAX_LENGTH - 150;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) onSend();
    }
  }

  return (
    <div
      className={cn(
        "group rounded-card border bg-surface-1 transition-[border-color,background-color,box-shadow] duration-fast",
        "focus-within:border-accent-border focus-within:bg-surface-2 focus-within:ring-1 focus-within:ring-accent/20",
      )}
    >
      <label htmlFor="composer-input" className="sr-only">
        Message Northstar Desk support
      </label>
      <textarea
        id="composer-input"
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about your account, billing, or setup…"
        maxLength={MAX_LENGTH + 50}
        aria-describedby="composer-hint"
        className="max-h-40 min-h-12 w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-base leading-relaxed text-ink placeholder:text-ink-muted focus:outline-hidden sm:text-[15px]"
      />
      <div className="flex items-center gap-3 px-3.5 pb-3 pt-1">
        <p
          id="composer-hint"
          className="hidden items-center gap-1.5 text-[11px] text-ink-muted opacity-60 transition-opacity duration-fast focus-within:opacity-100 sm:flex group-focus-within:opacity-100"
        >
          <Kbd>Enter</Kbd> to send
          <span aria-hidden="true">·</span>
          <Kbd className="ml-1">Shift + Enter</Kbd> new line
        </p>
        {nearLimit && (
          <span
            className={cn(
              "text-[11px] tabular-nums",
              value.length > MAX_LENGTH ? "text-danger-ink" : "text-ink-muted"
            )}
          >
            {value.length}/{MAX_LENGTH}
          </span>
        )}
        <button
          type="button"
          disabled={!canSend}
          onClick={onSend}
          aria-label={busy ? "Sending message" : "Send message"}
          aria-busy={busy || undefined}
          className={cn(
            "ml-auto flex size-9 shrink-0 items-center justify-center rounded-full transition-all duration-fast",
            "bg-accent text-on-accent hover:bg-accent-hover active:scale-95",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {busy ? (
            <span aria-hidden="true" className="flex items-center gap-1">
              <span className="size-1 animate-pulse rounded-full bg-on-accent [animation-delay:0ms]" />
              <span className="size-1 animate-pulse rounded-full bg-on-accent [animation-delay:200ms]" />
              <span className="size-1 animate-pulse rounded-full bg-on-accent [animation-delay:400ms]" />
            </span>
          ) : (
            <ArrowUp aria-hidden="true" className="size-4" />
          )}
        </button>
      </div>
    </div>
  );
}
