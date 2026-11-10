"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, RefreshCw } from "lucide-react";
import {
  api,
  ApiError,
  type ApiDocument,
  type ApiDocumentStatus,
  type ApiKnowledgeStatus,
} from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";

const STATUS_VARIANT: Record<
  ApiDocumentStatus,
  "success" | "warning" | "info" | "danger" | "neutral"
> = {
  READY: "success",
  PENDING: "warning",
  PROCESSING: "info",
  FAILED: "danger",
};

const KNOWLEDGE_LABEL: Record<ApiKnowledgeStatus, string> = {
  approved: "Approved",
  challenge_fixture: "Challenge fixture",
  archived: "Archived",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Knowledge base panel — embedded as a tab inside the staff workspace.
 * Every stored document with the backend's real processing status and
 * chunk counts. Read-only by design — ingestion is seeded from
 * `backend/knowledge/` and exposed through the documents API.
 */
export function KnowledgePanel() {
  const [documents, setDocuments] = useState<ApiDocument[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDocuments(await api.documents.list());
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not load the knowledge base.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const approved = documents?.filter((doc) => doc.knowledgeStatus === "approved") ?? [];
  const ready = approved.filter((doc) => doc.status === "READY");
  const chunks = approved.reduce((total, doc) => total + doc.chunkCount, 0);

  return (
    <div
      role="tabpanel"
      aria-label="Knowledge base"
      className="min-h-0 flex-1 overflow-y-auto bg-canvas text-ink"
    >
      <PageContainer size="wide">
        <PageHeader
          title="Knowledge base"
          description="The synthetic Northstar Desk help articles the assistant can search. Status and chunk counts come from the real ingestion pipeline."
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void load()}
              loading={loading}
            >
              {!loading && <RefreshCw aria-hidden="true" />}
              Refresh
            </Button>
          }
        />

        <div className="mb-6 flex flex-wrap items-center gap-2">
          <Badge variant="accent">Synthetic demo data</Badge>
          <Badge variant="neutral">{approved.length} approved documents</Badge>
          <Badge variant="neutral">{ready.length} ready for retrieval</Badge>
          <Badge variant="neutral">{chunks} indexed chunks</Badge>
        </div>

        {loading && documents === null ? (
          <div className="space-y-3" aria-label="Loading documents">
            {[0, 1, 2, 3].map((row) => (
              <div
                key={row}
                className="rounded-card border border-line bg-surface-1 p-4"
              >
                <Skeleton className="h-4 w-64" />
                <Skeleton className="mt-2 h-3 w-96 max-w-full" />
                <Skeleton className="mt-3 h-3 w-40" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="rounded-card border border-line bg-surface-1">
            <ErrorState
              title="Knowledge base unavailable"
              description={error}
              onRetry={() => void load()}
            />
          </div>
        ) : !documents || documents.length === 0 ? (
          <div className="rounded-card border border-line bg-surface-1">
            <EmptyState
              icon={<BookOpen className="size-5" />}
              title="No documents yet"
              description="Seeded help articles appear here after the backend starts and ingests backend/knowledge/."
            />
          </div>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <article
                key={doc.id}
                className="rounded-card border border-line bg-surface-1 p-4 transition-colors duration-fast hover:border-line-strong"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="font-display text-[15px] font-semibold tracking-tight text-ink">
                      {doc.title}
                    </h2>
                    <p className="mt-1 font-mono text-[11px] text-ink-muted">
                      {doc.source ?? doc.id}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={STATUS_VARIANT[doc.status]}>
                      {doc.status === "READY"
                        ? "Ready"
                        : doc.status === "PROCESSING"
                          ? "Processing"
                          : doc.status === "PENDING"
                            ? "Pending"
                            : "Failed"}
                    </Badge>
                    <Badge variant="neutral">
                      {KNOWLEDGE_LABEL[doc.knowledgeStatus]}
                    </Badge>
                  </div>
                </div>

                <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-ink-secondary">
                  <div className="flex items-center gap-1.5">
                    <dt className="text-ink-muted">Chunks</dt>
                    <dd className="tabular-nums">{doc.chunkCount}</dd>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <dt className="text-ink-muted">Updated</dt>
                    <dd>{formatDate(doc.updatedAt)}</dd>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <dt className="text-ink-muted">Processed</dt>
                    <dd>{formatDate(doc.processedAt)}</dd>
                  </div>
                </dl>

                {doc.failureReason && (
                  <p className="mt-3 rounded-control border border-danger-border bg-danger-soft p-2.5 text-xs text-danger-ink">
                    {doc.failureReason}
                  </p>
                )}
              </article>
            ))}
          </div>
        )}

        <p className="mt-6 text-[11px] leading-relaxed text-ink-muted">
          Northstar Desk is a fictional SaaS company used for this demo. All
          documents and customer information are synthetic.
        </p>
      </PageContainer>
    </div>
  );
}
