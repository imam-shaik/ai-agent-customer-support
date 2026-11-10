import type { ComponentPropsWithoutRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors duration-fast",
  {
    variants: {
      variant: {
        neutral: "border-line bg-surface-2 text-ink-secondary",
        accent: "border-accent-border bg-accent-soft text-accent-ink",
        info: "border-info-border bg-info-soft text-info-ink",
        success: "border-success-border bg-success-soft text-success-ink",
        warning: "border-warning-border bg-warning-soft text-warning-ink",
        danger: "border-danger-border bg-danger-soft text-danger-ink",
        outline: "border-line-strong bg-transparent text-ink-secondary",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends Omit<ComponentPropsWithoutRef<"span">, "children">,
    VariantProps<typeof badgeVariants> {
  children?: React.ReactNode;
}

/** Compact label chip: tags, metadata, low-key counts. */
export function Badge({ className, variant, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {children}
    </span>
  );
}
