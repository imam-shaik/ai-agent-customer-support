import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends ComponentPropsWithoutRef<"div"> {
  /** "overlay" adds the floating-layer shadow — reserved for lifted cards. */
  elevation?: "flat" | "overlay";
}

/** Content container: border-first elevation, 10px radius. */
export function Card({ className, elevation = "flat", ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-surface-1",
        elevation === "overlay" && "shadow-overlay",
        className
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: ComponentPropsWithoutRef<"div">) {
  return (
    <div
      className={cn("flex items-start justify-between gap-4 border-b border-line px-6 py-4", className)}
      {...props}
    />
  );
}

interface CardTitleProps {
  as?: "h2" | "h3" | "h4" | "p" | "div";
  className?: string;
  children: ReactNode;
}

export function CardTitle({ as: Comp = "h3", className, children }: CardTitleProps) {
  return (
    <Comp className={cn("font-display text-[15px] font-semibold tracking-tight text-ink", className)}>
      {children}
    </Comp>
  );
}

export function CardDescription({ className, ...props }: ComponentPropsWithoutRef<"p">) {
  return (
    <p className={cn("text-sm leading-relaxed text-ink-secondary", className)} {...props} />
  );
}

export function CardContent({ className, ...props }: ComponentPropsWithoutRef<"div">) {
  return <div className={cn("px-6 py-5", className)} {...props} />;
}

export function CardFooter({ className, ...props }: ComponentPropsWithoutRef<"div">) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 border-t border-line bg-surface-2/40 px-6 py-4",
        className
      )}
      {...props}
    />
  );
}
