import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

// Primary and destructive use a tinted fill (10/16/22% light, 16/22/30% dark
// for rest/hover/pressed), a saturated border and a contrast-safe label. The
// focus ring comes from the global :focus-visible rule in app.css.
const buttonVariants = cva(
  "inline-flex max-w-full shrink-0 items-center justify-center whitespace-nowrap border border-transparent font-medium text-ui transition-colors duration-150 select-none disabled:pointer-events-none disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-primary-tint-border bg-primary-tint text-primary-label hover:bg-primary-tint-hover active:bg-primary-tint-active",
        destructive:
          "border-destructive/30 bg-destructive/10 text-status-error-label hover:bg-destructive/16 active:bg-destructive/22 dark:border-destructive/35 dark:bg-destructive/16 dark:hover:bg-destructive/22 dark:active:bg-destructive/30",
        outline:
          "border-border bg-card text-foreground hover:border-border-hover hover:bg-interactive-hover active:bg-interactive-active",
        secondary:
          "border-border bg-secondary text-secondary-foreground hover:bg-interactive-hover active:bg-interactive-active",
        ghost: "text-foreground hover:bg-interactive-hover active:bg-interactive-active",
        link: "text-primary-label underline-offset-4 hover:underline",
        // Selection, never the primary action: neutral fill and normal text.
        chip: "border-border bg-transparent text-foreground hover:bg-interactive-hover active:bg-interactive-active aria-pressed:bg-selection data-[selected=true]:bg-selection",
      },
      size: {
        default: "h-9 gap-1.5 rounded-control px-3",
        sm: "h-8 gap-1 rounded-small px-3",
        // Inside a line of text, such as a [n] citation marker: the line sets the height.
        inline: "h-auto gap-0.5 px-0.5 text-[length:inherit]",
        xs: "h-6 gap-1 rounded-small px-2 text-meta [&_svg:not([class*='size-'])]:size-3",
        icon: "size-9 rounded-control",
        "icon-sm": "size-8 rounded-small",
        "icon-xs": "size-6 rounded-small [&_svg:not([class*='size-'])]:size-3",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

/**
 * Button with the OMRS treatment. Renders `type="button"` unless the caller
 * sets another type, so a button inside a form never submits by accident.
 */
function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  if (asChild) {
    return (
      <Slot
        data-slot="button"
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  }
  return (
    <button
      data-slot="button"
      type={type ?? "button"}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
