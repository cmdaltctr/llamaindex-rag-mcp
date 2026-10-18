import { Info } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../components/ui/button";
import { Popover } from "../components/ui/popover";

interface InfoPopoverProps {
  /** The accessible name of the info button, for example "About the Ingest pipeline". */
  label: string;
  children: ReactNode;
}

/**
 * An "i" button that opens a small panel of help text on click. Escape, a click
 * elsewhere or a second click closes it, and Escape returns focus to the button.
 * It adds detail only: put nothing here that the user must read to finish a task.
 */
export function InfoPopover({ label, children }: InfoPopoverProps) {
  return (
    <Popover
      slot="info-popover-content"
      trigger={(props) => (
        <Button variant="ghost" size="icon-xs" aria-label={label} {...props}>
          <Info aria-hidden="true" />
        </Button>
      )}
    >
      {children}
    </Popover>
  );
}
