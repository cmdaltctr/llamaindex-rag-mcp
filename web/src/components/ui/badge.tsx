import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, CSSProperties, ReactNode } from "react";
import { cn } from "../../lib/utils";

// Status badges use a 10% fill, a status-colour border and a label colour
// mixed towards the text colour, because raw status colours fail WCAG AA as
// normal text. The status value must always appear as the badge text.
const badgeVariants = cva(
  "inline-flex w-fit max-w-full shrink-0 items-center gap-1 overflow-hidden whitespace-nowrap rounded-small border px-2 py-0.5 text-meta font-medium [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "border-border bg-secondary text-secondary-foreground",
        accent: "border-primary-tint-border bg-primary-tint text-primary-label",
        error: "border-status-error bg-status-error/10 text-status-error-label",
        warning: "border-status-warning bg-status-warning/10 text-status-warning-label",
        success: "border-status-success bg-status-success/10 text-status-success-label",
        info: "border-status-info bg-status-info/10 text-status-info-label",
        // Profile labels and node kinds: a stable hue per label. The border takes the text colour.
        hue: "border-current bg-transparent text-[oklch(0.42_0.13_var(--badge-hue))] dark:text-[oklch(0.8_0.13_var(--badge-hue))]",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

type BadgeProps = ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & {
    asChild?: boolean;
    /** For the `hue` variant: overrides the hue hashed from the label (0 to 359). */
    hue?: number;
  };

/** A stable hue (0 to 359) for a label, so one label has one colour everywhere. */
function hueFor(label: string): number {
  let hash = 0;
  for (const char of label) hash = (hash * 31 + (char.codePointAt(0) ?? 0)) >>> 0;
  return hash % 360;
}

function textOf(children: ReactNode): string {
  return typeof children === "string" || typeof children === "number" ? String(children) : "";
}

function Badge({ className, variant, asChild = false, hue, style, children, ...props }: BadgeProps) {
  const Comp = asChild ? Slot : "span";
  const hueStyle =
    variant === "hue" ? ({ "--badge-hue": hue ?? hueFor(textOf(children)), ...style } as CSSProperties) : style;
  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} style={hueStyle} {...props}>
      {children}
    </Comp>
  );
}

export { Badge, badgeVariants, hueFor };
