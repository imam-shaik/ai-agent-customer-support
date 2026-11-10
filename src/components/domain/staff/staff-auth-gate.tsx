"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { LogIn, ShieldCheck, UserPlus } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, ApiError, type ApiStaffUser } from "@/lib/api/client";
import { setToken } from "@/lib/staff/session";
import { cn } from "@/lib/utils";

type AuthMode = "create" | "signin";

interface StaffAuthGateProps {
  /** Called with the signed-in user after register/login succeeds. */
  onAuthenticated: (user: ApiStaffUser) => void;
}

/**
 * Staff sign-in / first-run account creation.
 *
 * The backend decides the initial screen: /auth/status reports whether
 * any staff account exists yet (first run → create account). Both modes
 * stay reachable via the tab row, so additional team members can be
 * created later. Failures are shown honestly from the API envelope —
 * unknown email and wrong password share one 401 message by design.
 */
export function StaffAuthGate({ onAuthenticated }: StaffAuthGateProps) {
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Which screen to open: create on first run, sign-in afterwards.
  useEffect(() => {
    let cancelled = false;
    api.auth
      .status()
      .then((status) => {
        if (!cancelled) setMode(status.hasStaffUser ? "signin" : "create");
      })
      .catch(() => {
        if (!cancelled) {
          setStatusError("Couldn't reach the sign-in service. Is the backend running?");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (submitting || mode === null) return;

      // Client-side validation mirrors the backend contract (8+ chars).
      const errors: typeof fieldErrors = {};
      if (mode === "create" && name.trim().length < 2) {
        errors.name = "Enter your name (at least 2 characters).";
      }
      if (email.trim().length === 0 || !email.includes("@")) {
        errors.email = "Enter a valid email address.";
      }
      if (password.length < (mode === "create" ? 8 : 1)) {
        errors.password =
          mode === "create" ? "Password must be at least 8 characters." : "Enter your password.";
      }
      setFieldErrors(errors);
      setFormError(Object.keys(errors).length > 0 ? null : formError);
      if (Object.keys(errors).length > 0) return;

      setSubmitting(true);
      setFormError(null);
      try {
        const session =
          mode === "create"
            ? await api.auth.register({ name: name.trim(), email: email.trim(), password })
            : await api.auth.login({ email: email.trim(), password });
        setToken(session.token);
        onAuthenticated(session.user);
      } catch (error) {
        if (error instanceof ApiError) {
          // 422 validation envelopes carry field-level details; the safe
          // message is shown for everything else (401/409/…).
          setFormError(error.message);
        } else {
          setFormError("Sign-in failed unexpectedly. Please try again.");
        }
        setSubmitting(false);
      }
    },
    [email, mode, name, onAuthenticated, password, submitting],
  );

  function switchMode(next: AuthMode) {
    setMode(next);
    setFieldErrors({});
    setFormError(null);
  }

  if (statusError) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-canvas px-4 text-center">
        <Logo showProduct />
        <p className="max-w-sm text-sm leading-relaxed text-ink-secondary">{statusError}</p>
        <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  const isCreate = mode === "create";

  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <header className="border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center px-4 md:px-6">
          <Logo showProduct />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <span className="inline-flex size-11 items-center justify-center rounded-full border border-accent-border bg-accent-soft text-accent-ink">
              <ShieldCheck aria-hidden="true" className="size-5" />
            </span>
            <h1 className="mt-3 font-display text-lg font-semibold tracking-tight text-ink">
              {isCreate ? "Create the staff login" : "Staff sign in"}
            </h1>
            <p className="mt-1 text-sm leading-relaxed text-ink-secondary">
              {isCreate
                ? "First run: create the team login you'll use for every future sign-in to the staff workspace."
                : "Sign in with the staff login created on first run to open the escalation queue."}
            </p>
          </div>

          {/* Mode tabs — create stays reachable after first run so extra
              team accounts can be added. */}
          <div
            role="tablist"
            aria-label="Authentication mode"
            className="mb-4 grid grid-cols-2 gap-1 rounded-control border border-line bg-surface-1 p-1"
          >
            {(
              [
                { key: "create", label: "Create account", icon: UserPlus },
                { key: "signin", label: "Sign in", icon: LogIn },
              ] as const
            ).map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={mode === tab.key}
                disabled={mode === null}
                onClick={() => switchMode(tab.key)}
                className={cn(
                  "flex items-center justify-center gap-1.5 rounded-control px-3 py-1.5 text-[13px] font-medium transition-colors duration-fast",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50",
                  mode === tab.key
                    ? "bg-surface-3 text-ink shadow-xs"
                    : "text-ink-secondary hover:text-ink",
                )}
              >
                <tab.icon aria-hidden="true" className="size-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          <form
            onSubmit={(event) => void handleSubmit(event)}
            className="rounded-card border border-line bg-surface-1 p-5 shadow-xs"
            noValidate
          >
            <div className="space-y-4">
              {isCreate && (
                <Field label="Full name" required error={fieldErrors.name}>
                  <Input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Maya Chen"
                    autoComplete="name"
                    maxLength={100}
                  />
                </Field>
              )}

              <Field label="Work email" required error={fieldErrors.email}>
                <Input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  maxLength={320}
                />
              </Field>

              <Field
                label="Password"
                required
                error={fieldErrors.password}
                hint={isCreate ? "At least 8 characters." : undefined}
              >
                <Input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={isCreate ? "Create a password" : "Your password"}
                  autoComplete={isCreate ? "new-password" : "current-password"}
                  maxLength={128}
                />
              </Field>

              {formError && (
                <p
                  role="alert"
                  className="rounded-control border border-danger-border bg-danger-soft p-2.5 text-xs leading-relaxed text-danger-ink"
                >
                  {formError}
                </p>
              )}

              <Button type="submit" className="w-full" loading={submitting} disabled={mode === null}>
                {isCreate ? "Create account & sign in" : "Sign in"}
              </Button>
            </div>
          </form>

          <p className="mt-4 text-center text-[11px] leading-relaxed text-ink-muted">
            Staff access only. Sessions expire automatically; sign-out invalidates
            the token on the server.
          </p>
        </div>
      </main>
    </div>
  );
}
