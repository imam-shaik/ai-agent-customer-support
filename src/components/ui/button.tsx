import type { ComponentPropsWithoutRef, ReactElement, ReactNode, Ref } from "react";
import { Slot } from "@radix-ui/react-slot";
import { LoaderCircle } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-control border border-transparent font-medium transition-[background-color,border-color,color,transform] duration-fast ease-standard disabled:pointer-events-none disabled:opacity-45 active:scale-[0.98] focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
  {
    variants: {
      variant: {
        default: "bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-pressed",
        secondary:
          "border-line bg-surface-2 text-ink hover:border-line-strong hover:bg-surface-3",
        ghost: "bg-transparent text-ink-secondary hover:bg-surface-2 hover:text-ink",
        danger:
          "border-danger-border bg-danger-soft text-danger-ink hover:bg-danger hover:text-on-accent",
        link: "bg-transparent text-accent-ink underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-[13px] [&_svg]:size-3.5",
        md: "h-9 px-4 text-sm [&_svg]:size-4",
        lg: "h-11 px-5 text-sm [&_svg]:size-[18px]",
        icon: "size-9 p-0 [&_svg]:size-4",
        "icon-sm": "size-8 p-0 [&_svg]:size-4",
      },
    },
    compoundVariants: [
      {
        variant: "link",
        size: ["sm", "md", "lg", "icon", "icon-sm"],
        className: "h-auto border-transparent px-0",
      },
    ],
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends Omit<ComponentPropsWithoutRef<"button">, "children">,
    VariantProps<typeof buttonVariants> {
  /** Render as the child element (e.g. <Link>), merging button styles. */
  asChild?: boolean;
  /** Show a spinner and block interaction (ignored with asChild). */
  loading?: boolean;
  ref?: Ref<HTMLButtonElement>;
  children?: ReactNode;
}

/**
 * Primary interaction primitive.
 * - variant: default (amber) | secondary | ghost | danger | link
 * - size: sm | md | lg | icon | icon-sm
 * - Always type="button" unless specified (avoids accidental form submits)
 */
export function Button({
  className,
  variant,
  size,
  asChild = false,
  loading = false,
  disabled,
  type,
  ref,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);

  if (asChild) {
    // asChild: children must be a single element; loading spinner is not injected.
    return (
      <Slot className={classes} aria-busy={loading || undefined} {...props}>
        {children as ReactElement}
      </Slot>
    );
  }

  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={classes}
      {...props}
    >
      {loading && <LoaderCircle className="shrink-0 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

Button.displayName = "Button";

export { buttonVariants };
