"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, ApiError, type ApiProviderSettings } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
/**
 * AI provider settings dialog (operator surface, both workspaces).
 *
 * Lets the operator paste NVIDIA keys here instead of editing
 * backend/.env by hand. Honesty rules:
 * - keys are submitted once to the server and never stored in the
 *   browser (no localStorage, cleared from state after use);
 * - the dialog shows only booleans + masked previews ("nvapi-…abcd");
 * - verification is a REAL provider call — a wrong key shows its error
 *   and is never reported as success;
 * - saved keys persist server-side until the operator changes them;
 * - keys are for LIVE mode; the header Demo/Live switch selects the
 *   deterministic local providers without touching saved keys.
 */
export function ProviderSettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [status, setStatus] = useState<ApiProviderSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [embeddingKey, setEmbeddingKey] = useState("");
  const [chatKey, setChatKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeTone, setNoticeTone] = useState<"ok" | "danger">("ok");

  const loadStatus = useCallback(async () => {
    setLoadError(null);
    try {
      setStatus(await api.providers.get());
    } catch {
      setLoadError("Could not load provider settings from the server.");
    }
  }, []);

  useEffect(() => {
    if (open) void loadStatus();
  }, [open, loadStatus]);

  function clearInputs() {
    setEmbeddingKey("");
    setChatKey("");
  }

  const payload = () => ({
    ...(embeddingKey.trim() ? { embeddingApiKey: embeddingKey.trim() } : {}),
    ...(chatKey.trim() ? { nvidiaApiKey: chatKey.trim() } : {}),
  });

  const hasInput = embeddingKey.trim().length > 0 || chatKey.trim().length > 0;

  async function handleVerify() {
    setVerifying(true);
    setNotice(null);
    try {
      const result = await api.providers.verify(payload());
      const lines: string[] = [];
      if (result.embedding) {
        lines.push(
          result.embedding.ok
            ? "Embedding key: verified against the live endpoint."
            : `Embedding key failed: ${result.embedding.error ?? "unknown error"}`,
        );
      }
      if (result.chat) {
        lines.push(
          result.chat.ok
            ? "Chat key: verified against the live endpoint."
            : `Chat key failed: ${result.chat.error ?? "unknown error"}`,
        );
      }
      const failed = [result.embedding, result.chat].some((item) => item && !item.ok);
      setNoticeTone(failed ? "danger" : "ok");
      setNotice(lines.join(" "));
    } catch (error) {
      setNoticeTone("danger");
      setNotice(
        error instanceof ApiError
          ? error.message
          : "Verification could not be completed.",
      );
    } finally {
      setVerifying(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setNotice(null);
    try {
      const next = await api.providers.saveKeys(payload());
      setStatus(next);
      clearInputs();
      setNoticeTone("ok");
      setNotice("Keys saved on the server. " + next.modeNote);
    } catch (error) {
      setNoticeTone("danger");
      setNotice(
        error instanceof ApiError
          ? error.message
          : "Saving the keys failed. Nothing was changed.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(value) => {
        onOpenChange(value);
        if (!value) {
          clearInputs();
          setNotice(null);
        }
      }}
      title="AI provider settings"
      description="Paste your NVIDIA API keys here — they are stored on the server (backend/.env), never in the browser."
      size="md"
    >
      <div className="space-y-4">
        {status && (
          <div className="space-y-2 rounded-control border border-line bg-surface-2 p-3 text-[13px]">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={status.llmProvider === "nvidia" ? "info" : "neutral"}>
                {status.llmProvider === "nvidia" ? "NVIDIA providers" : "Test providers"}
              </Badge>
              <Badge variant={status.embeddingKeyConfigured ? "success" : "neutral"}>
                Embedding key {status.embeddingKeyConfigured ? "set" : "missing"}
                {status.embeddingKeyMasked ? ` · ${status.embeddingKeyMasked}` : ""}
              </Badge>
              <Badge variant={status.llmKeyConfigured ? "success" : "neutral"}>
                Chat key {status.llmKeyConfigured ? "set" : "missing"}
                {status.llmKeyMasked ? ` · ${status.llmKeyMasked}` : ""}
              </Badge>
            </div>
            <p className="text-ink-secondary">{status.modeNote}</p>
          </div>
        )}
        {loadError && <p className="text-[13px] text-danger-ink">{loadError}</p>}

        <Field label="Embedding API key" hint="Used for indexing and retrieval (nvapi-…).">
          <Input
            type="password"
            autoComplete="off"
            placeholder="nvapi-…"
            value={embeddingKey}
            onChange={(event) => setEmbeddingKey(event.target.value)}
          />
        </Field>
        <Field label="Chat API key" hint="Used by the answer model (can be the same key).">
          <Input
            type="password"
            autoComplete="off"
            placeholder="nvapi-…"
            value={chatKey}
            onChange={(event) => setChatKey(event.target.value)}
          />
        </Field>

        <p className="flex items-start gap-1.5 text-[12px] text-ink-muted">
          <ShieldCheck aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          Keys are sent once to your local backend and saved to backend/.env.
          They are never displayed again — only a masked preview — and never
          logged. Verify checks the key against the real NVIDIA endpoint.
        </p>

        {notice && (
          <p
            role="status"
            className={
              noticeTone === "ok"
                ? "rounded-control border border-line bg-surface-2 p-2.5 text-[13px] text-ink-secondary"
                : "rounded-control border border-line bg-surface-2 p-2.5 text-[13px] text-danger-ink"
            }
          >
            {notice}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={!hasInput || verifying || saving}
            onClick={() => void handleVerify()}
          >
            {verifying ? "Verifying…" : "Verify with provider"}
          </Button>
          <Button
            size="sm"
            disabled={!hasInput || saving || verifying}
            onClick={() => void handleSave()}
          >
            {saving ? "Saving…" : "Save keys"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
