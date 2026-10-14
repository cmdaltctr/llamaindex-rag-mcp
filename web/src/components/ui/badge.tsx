import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
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
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

type BadgeProps = ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean };

function Badge({ className, variant, asChild = false, ...props }: BadgeProps) {
  const Comp = asChild ? Slot : "span";
  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
