import { useRef } from "react";

/**
 * Props for a Radix `DialogContent` that is opened by state, not by a `DialogTrigger`.
 * Radix returns focus only to a trigger, so these remember the element that had focus
 * when the dialog opened and focus it again when the dialog closes.
 */
export function useReturnFocus() {
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus: () => {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    },
    onCloseAutoFocus: (event: Event) => {
      event.preventDefault();
      opener.current?.focus();
    },
  };
}
