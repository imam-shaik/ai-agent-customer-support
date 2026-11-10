import type { ReactNode } from "react";
import { Breadcrumbs, type Crumb } from "./breadcrumbs";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  breadcrumbs?: Crumb[];
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned actions (filters, primary action). */
  actions?: ReactNode;
  className?: string;
}

/** Page-level heading block: breadcrumb, h1, supporting line, actions. */
export function PageHeader({
  breadcrumbs,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("mb-6", className)}>
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} className="mb-3" />}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink md:text-[28px]">
            {title}
          </h1>
          {description && (
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-secondary">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
