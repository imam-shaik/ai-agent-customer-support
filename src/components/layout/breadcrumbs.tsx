import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  /** Omit on the current (last) page. */
  href?: string;
}

interface BreadcrumbsProps {
  items: Crumb[];
  className?: string;
}

/** Hierarchical location — useful in staff views (Queue › Ticket). */
export function Breadcrumbs({ items, className }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className={cn("text-xs text-ink-muted", className)}>
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && (
              <ChevronRight aria-hidden="true" className="size-3 text-ink-muted/60" />
            )}
            {item.href ? (
              <Link
                href={item.href}
                className="rounded-[3px] transition-colors duration-fast hover:text-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
              >
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-ink-secondary">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
