"use client";

import { createContext, useContext, useId, useMemo, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface FieldContextValue {
  id: string;
  describedBy?: string;
  invalid: boolean;
}

const FieldContext = createContext<FieldContextValue | null>(null);

/** Controls read this to inherit id, description, and invalid state. */
export function useFieldContext(): FieldContextValue | null {
  return useContext(FieldContext);
}

interface FieldProps {
  label: ReactNode;
  /** Helper text, shown until an error replaces it. */
  hint?: ReactNode;
  /** Error message; presence switches the control to invalid state. */
  error?: ReactNode;
  required?: boolean;
  className?: string;
  /** Override the auto-generated id (label htmlFor, controls). */
  id?: string;
  children: ReactNode;
}

/**
 * Form field wrapper: visible label, hint/error with proper ids,
 * and a context that Input/Textarea/Select consume automatically.
 *
 *   <Field label="Work email" error={errors.email}>
 *     <Input type="email" placeholder="you@company.com" />
 *   </Field>
 */
export function Field({
  label,
  hint,
  error,
  required = false,
  className,
  id,
  children,
}: FieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const invalid = Boolean(error);
  const describedBy = invalid ? errorId : hint ? hintId : undefined;

  const context = useMemo<FieldContextValue>(
    () => ({ id: fieldId, describedBy, invalid }),
    [fieldId, describedBy, invalid]
  );

  return (
    <FieldContext.Provider value={context}>
      <div className={cn("flex flex-col gap-1.5", className)}>
        <label htmlFor={fieldId} className="text-[13px] font-medium text-ink-secondary">
          {label}
          {required && (
            <>
              <span aria-hidden="true" className="ml-1 text-accent">
                *
              </span>
              <span className="sr-only"> (required)</span>
            </>
          )}
        </label>
        {children}
        {invalid ? (
          <p id={errorId} role="alert" className="text-xs text-danger-ink">
            {error}
          </p>
        ) : hint ? (
          <p id={hintId} className="text-xs text-ink-muted">
            {hint}
          </p>
        ) : null}
      </div>
    </FieldContext.Provider>
  );
}
