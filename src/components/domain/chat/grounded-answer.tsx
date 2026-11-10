"use client";

import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { parseAnswerMarkers } from "@/lib/support/markers";
import type { ApiCitation } from "@/lib/api/client";

interface GroundedAnswerProps {
  text: string;
  citations: ApiCitation[];
  /** Opens the evidence sheet for this answer's stored sources. */
  onInspect?: () => void;
}

/**
 * A grounded answer, answer-first: prose directly on the canvas (the
 * easiest content to read on the screen), then a quiet trust row —
 * grounding indicator + numbered source chips that open the evidence
 * sheet. Inline [^n] markers still render for demo/legacy transcripts.
 */
export function GroundedAnswer({ text, citations, onInspect }: GroundedAnswerProps) {
  const segments = parseAnswerMarkers(text);
  const hasMarkers = segments.some((segment) => segment.type === "citation");

  return (
    <div className="min-w-0">
      <div className="max-w-[65ch] text-[16px] leading-[1.7] text-ink">
        {segments.map((segment, index) => {
          if (segment.type === "text") return <span key={index}>{segment.value}</span>;
          return (
            <button
              key={index}
              type="button"
              onClick={onInspect}
              aria-label={`Source ${segment.index}`}
              className="mx-0.5 inline-flex size-6 translate-y-[-1px] items-center justify-center rounded-[6px] border border-accent-border bg-accent-soft align-baseline font-mono text-[11px] font-medium text-accent-ink transition-all duration-fast hover:-translate-y-px hover:border-accent hover:shadow-pop focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 active:translate-y-0"
            >
              {segment.index}
            </button>
          );
        })}
      </div>

      {/* Trust row: grounding indicator + numbered source chips */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-success-ink">
          <ShieldCheck aria-hidden="true" className="size-3.5" />
          Grounded in approved documentation
        </span>
        <span className="hidden items-center gap-1 sm:flex" role="group" aria-label="Sources">
          {citations.map((citation, index) => (
            <button
              key={`${citation.docId}-${citation.sectionId}-${index}`}
              type="button"
              onClick={onInspect}
              title={
                (citation.documentTitle?.trim() || citation.docId) +
                (citation.sectionTitle?.trim() ? ` — ${citation.sectionTitle.trim()}` : "")
              }
              className="inline-flex size-6 items-center justify-center rounded-[6px] border border-line bg-surface-2 font-mono text-[11px] font-medium text-ink-secondary transition-all duration-fast hover:-translate-y-px hover:border-accent-border hover:bg-accent-soft hover:text-accent-ink hover:shadow-pop focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 active:translate-y-0"
            >
              {index + 1}
            </button>
          ))}
        </span>
        {onInspect && (
          <button
            type="button"
            onClick={onInspect}
            className={cn(
              "text-xs font-medium text-ink-secondary underline-offset-4 transition-colors duration-fast",
              "hover:text-ink hover:underline",
              "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded-control",
            )}
          >
            {hasMarkers || citations.length > 0 ? "View sources" : "Sources"}
          </button>
        )}
      </div>
    </div>
  );
}
