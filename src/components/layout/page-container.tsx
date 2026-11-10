import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

const SIZES = {
  content: "max-w-3xl",
  wide: "max-w-6xl",
  full: "max-w-[1440px]",
} as const;

interface PageContainerProps extends ComponentPropsWithoutRef<"div"> {
  size?: keyof typeof SIZES;
}

/** Standard page gutter + max-width. Most pages live inside `wide`. */
export function PageContainer({ size = "wide", className, ...props }: PageContainerProps) {
  return (
    <div
      className={cn("mx-auto w-full px-4 py-6 md:px-6 md:py-8", SIZES[size], className)}
      {...props}
    />
  );
}
