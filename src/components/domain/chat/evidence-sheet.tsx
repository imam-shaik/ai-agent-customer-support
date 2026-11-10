"use client";

import { Drawer } from "@/components/ui/drawer";
import { SourceCard } from "./source-card";
import { ShieldCheck } from "lucide-react";
import type { ApiCitation } from "@/lib/api/client";

interface EvidenceSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  citations: ApiCitation[];
  /** Short context line, e.g. the answer's opening words. */
  context?: string;
}

/**
 * On-demand evidence inspection: a side sheet listing the approved
 * sources that support one answer (desktop) sliding over the
 * conversation (mobile). Renders exactly the stored evidence snapshot —
 * never invented content.
 */
export function EvidenceSheet({ open, onOpenChange, citations, context }: EvidenceSheetProps) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      side="right"
      title={
        <span className="flex items-center gap-2 text-sm font-medium text-ink">
          <ShieldCheck aria-hidden="true" className="size-4 text-success-ink" />
          Approved sources
          <span className="font-normal text-ink-muted">
            · {citations.length}
          </span>
        </span>
      }
      description={
        context
          ? `Evidence for the answer beginning “${context.slice(0, 80)}${context.length > 80 ? "…" : ""}”`
          : "The documentation excerpts that support this answer"
      }
      className="sm:max-w-[460px]"
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        {citations.length === 0 ? (
          <p className="rounded-control border border-dashed border-line px-3.5 py-4 text-xs leading-relaxed text-ink-muted">
            This answer has no stored citations.
          </p>
        ) : (
          citations.map((citation, index) => (
            <div key={`${citation.docId}-${citation.sectionId}-${index}`} className="flex gap-2.5">
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-[6px] border border-accent-border bg-accent-soft font-mono text-[11px] font-medium text-accent-ink">
                {index + 1}
              </span>
              <SourceCard
                citation={citation}
                className="min-w-0 flex-1 rounded-card border border-line bg-surface-1 p-3.5"
              />
            </div>
          ))
        )}
        <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
          Snapshots are captured when each answer is generated, so what you see here is exactly
          what supported it — even if the documentation changes later.
        </p>
      </div>
    </Drawer>
  );
}
