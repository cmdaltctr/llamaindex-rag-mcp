import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { ChevronDown, type LucideIcon } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

const Accordion = AccordionPrimitive.Root;

function AccordionItem({ className, ...props }: ComponentProps<typeof AccordionPrimitive.Item>) {
  return (
    <AccordionPrimitive.Item
      data-slot="accordion-item"
      className={cn("border-b border-border last:border-b-0", className)}
      {...props}
    />
  );
}

interface AccordionTriggerProps extends ComponentProps<typeof AccordionPrimitive.Trigger> {
  /** Shown before the title. Hidden from assistive technology, so the title stays the name. */
  icon?: LucideIcon;
}

// The header is an h2 because the page heading is the h1. Radix defaults to h3.
// The focus ring comes from the global :focus-visible rule in app.css.
function AccordionTrigger({ className, children, icon: Icon, ...props }: AccordionTriggerProps) {
  return (
    <AccordionPrimitive.Header asChild>
      <h2 className="flex">
        <AccordionPrimitive.Trigger
          data-slot="accordion-trigger"
          className={cn(
            "group flex min-h-11 flex-1 items-center gap-2 px-3 py-2 text-start text-ui font-semibold transition-colors duration-150 hover:bg-interactive-hover",
            className,
          )}
          {...props}
        >
          {Icon ? <Icon aria-hidden="true" className="size-4 shrink-0" /> : null}
          <span className="min-w-0 flex-1">{children}</span>
          <ChevronDown
            aria-hidden="true"
            className="size-4 shrink-0 transition-transform duration-150 group-data-[state=open]:rotate-180"
          />
        </AccordionPrimitive.Trigger>
      </h2>
    </AccordionPrimitive.Header>
  );
}

function AccordionContent({ className, children, ...props }: ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content data-slot="accordion-content" className="text-ui" {...props}>
      <div className={cn("flex flex-col gap-3 px-3 pb-3", className)}>{children}</div>
    </AccordionPrimitive.Content>
  );
}

export { Accordion, AccordionContent, AccordionItem, AccordionTrigger };
