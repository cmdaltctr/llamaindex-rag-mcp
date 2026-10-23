import { useEffect, useState, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

/** How long a navigation tooltip stays up while the pointer rests on its item. */
export const NAV_TOOLTIP_MS = 3000;

/**
 * Names a navigation item on hover or focus. It opens with no delay, so a user
 * can sweep the icon column, and closes itself after three seconds so it never
 * covers the page for long. Wrap the tree in a `TooltipProvider`.
 */
export function NavTooltip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => setOpen(false), NAV_TOOLTIP_MS);
    return () => window.clearTimeout(timer);
  }, [open]);
  return (
    <Tooltip open={open} onOpenChange={setOpen} delayDuration={0}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
