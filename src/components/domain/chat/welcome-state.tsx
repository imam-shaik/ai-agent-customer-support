"use client";

import { ArrowRight } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { NorthstarLogo } from "@/components/brand/NorthstarLogo";
import { cn } from "@/lib/utils";
import type { SupportTopic } from "@/lib/support/knowledge";

interface WelcomeStateProps {
  topics: SupportTopic[];
  selectedTopicId: string;
  onSelectTopic: (id: string) => void;
  onAsk: (question: string) => void;
}

/**
 * Support entry — a workspace opening screen, not a landing page:
 * identity, scope of help, topic picker, starter questions.
 * Content enters in a short staggered sequence (≤ 400ms total);
 * `prefers-reduced-motion` collapses the sequence via globals.css.
 */
export function WelcomeState({
  topics,
  selectedTopicId,
  onSelectTopic,
  onAsk,
}: WelcomeStateProps) {
  const selected = topics.find((topic) => topic.id === selectedTopicId) ?? topics[0];

  return (
    <div className="mx-auto max-w-2xl animate-fade-in px-1 py-10 md:py-14">
      <div
        className="flex flex-wrap items-center justify-between gap-4 animate-rise-in"
        style={{ animationDelay: "0ms" }}
      >
        <NorthstarLogo />
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-muted">
          <LogoMark className="size-3.5" aria-hidden="true" />
          Powered by Vilasat AI
        </span>
      </div>

      <h1
        className="mt-7 font-display text-2xl font-semibold tracking-tight text-ink animate-rise-in"
        style={{ animationDelay: "60ms" }}
      >
        How can we help you today?
      </h1>

      <p
        className="mt-2.5 text-[15px] leading-relaxed text-ink-secondary animate-rise-in"
        style={{ animationDelay: "120ms" }}
      >
        I can help with account access, billing, subscriptions, and product setup — answering
        only from Northstar Desk's approved documentation, and showing the source for
        every factual answer. If I can't confirm something, I'll tell you rather
        than guess.
      </p>

      <section
        aria-labelledby="topics-label"
        className="mt-8 animate-rise-in"
        style={{ animationDelay: "180ms" }}
      >
        <h2
          id="topics-label"
          className="text-[11px] font-medium uppercase tracking-wide text-ink-muted"
        >
          What do you need help with?
        </h2>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-labelledby="topics-label">
          {topics.map((topic) => (
            <button
              key={topic.id}
              type="button"
              aria-pressed={topic.id === selected.id}
              onClick={() => onSelectTopic(topic.id)}
              className={cn(
                "rounded-control border px-3.5 py-2 text-left text-sm font-medium transition-all duration-fast",
                "hover:-translate-y-px active:translate-y-0 active:scale-[0.99]",
                "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
                topic.id === selected.id
                  ? "border-accent-border bg-accent-soft text-accent-ink"
                  : "border-line bg-surface-1 text-ink-secondary hover:border-line-strong hover:bg-surface-2 hover:text-ink"
              )}
            >
              {topic.label}
              <span
                className={cn(
                  "ml-2 hidden text-[11px] font-normal sm:inline",
                  topic.id === selected.id ? "text-accent-ink/80" : "text-ink-muted"
                )}
              >
                {topic.description}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section
        aria-labelledby="questions-label"
        className="mt-7 animate-rise-in"
        style={{ animationDelay: "240ms" }}
      >
        <h2
          id="questions-label"
          className="text-[11px] font-medium uppercase tracking-wide text-ink-muted"
        >
          Popular questions
        </h2>
        <ul className="mt-3 space-y-2">
          {selected.questions.map((question, index) => (
            <li
              key={question}
              className="animate-rise-in"
              style={{ animationDelay: `${300 + index * 40}ms` }}
            >
              <button
                type="button"
                onClick={() => onAsk(question)}
                className="group flex w-full items-center justify-between gap-3 rounded-card border border-line bg-surface-1 px-4 py-3 text-left text-sm text-ink-secondary transition-all duration-fast hover:-translate-y-px hover:border-line-strong hover:bg-surface-2 hover:text-ink hover:shadow-pop focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 active:translate-y-0"
              >
                <span>{question}</span>
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-ink-muted transition-all duration-fast group-hover:translate-x-0.5 group-hover:text-accent-ink"
                />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-10 text-[11px] leading-relaxed text-ink-muted">
        Your conversation stays in this workspace and is only used to support your request.
      </p>
    </div>
  );
}
