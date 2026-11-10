"use client";

import { Badge } from "@/components/ui/badge";
import type { ApiCitation } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface SourceCardProps {
  citation: ApiCitation;
  /** `panel` = in-conversation evidence; `rail` = compact sources list. */
  size?: "panel" | "rail";
  className?: string;
}

/**
 * One approved source: document title, section reference, and the exact
 * supporting snippet — rendered ONLY from the backend's stored evidence
 * snapshot. Missing metadata degrades honestly to the raw identifiers;
 * nothing is invented locally.
 */
export function SourceCard({ citation, size = "panel", className }: SourceCardProps) {
  const title = citation.documentTitle?.trim() || citation.docId;
  const sectionTitle = citation.sectionTitle?.trim() || citation.sectionId;
  const snippet = citation.snippet?.trim() || "";

  return (
    <article className={cn("min-w-0", className)}>
      <div className="flex items-start justify-between gap-3">
        <p
          className={cn(
            "min-w-0 break-words font-medium leading-snug text-ink",
            size === "rail" ? "text-[13px]" : "text-sm",
          )}
        >
          {title}
        </p>
        <Badge variant="success" className="shrink-0">
          Approved
        </Badge>
      </div>
      <p
        className={cn(
          "mt-1 break-words font-medium text-ink-muted",
          size === "rail" ? "text-[10px]" : "text-xs",
        )}
      >
        {sectionTitle}
      </p>
      {snippet && (
        <blockquote
          className={cn(
            "mt-2 border-l-2 border-line pl-3 leading-relaxed text-ink-secondary",
            size === "rail" ? "text-[11px]" : "text-xs",
          )}
        >
          {snippet}
        </blockquote>
      )}
    </article>
  );
}
