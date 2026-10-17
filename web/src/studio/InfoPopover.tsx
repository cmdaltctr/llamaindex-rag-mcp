import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "../components/ui/button";

interface InfoPopoverProps {
  /** The accessible name of the info button, for example "About the Ingest pipeline". */
  label: string;
  children: ReactNode;
}

const PANEL_WIDTH = 288;
const EDGE = 8;

/** Where the panel goes: under the button, moved left when it would run off the right edge of the screen. */
function placeUnder(button: HTMLElement): { top: number; left: number } {
  const rect = button.getBoundingClientRect();
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - PANEL_WIDTH - EDGE));
  return { top: rect.bottom + 4, left };
}

/**
 * An "i" button that opens a small panel of help text on click. Escape, a click
 * elsewhere or a second click closes it, and Escape returns focus to the button.
 * The panel is drawn on the page body, so a clipping ancestor (such as the sliding
 * header) cannot cut it off. It adds detail only: put nothing here that the user
 * must read to finish a task.
 */
export function InfoPopover({ label, children }: InfoPopoverProps) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const open = position !== null;

  useEffect(() => {
    if (!open) return;
    const close = () => setPosition(null);
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && !button.current?.contains(target) && !panel.current?.contains(target)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      close();
      button.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    // A fixed panel would drift from its button when the page moves or resizes, so close it.
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  return (
    <>
      <Button
        ref={button}
        variant="ghost"
        size="icon-xs"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setPosition((current) => (current ? null : button.current ? placeUnder(button.current) : null))}
      >
        <Info aria-hidden="true" />
      </Button>
      {position &&
        createPortal(
          <div
            ref={panel}
            id={panelId}
            data-slot="info-popover-content"
            style={{ top: position.top, left: position.left, width: PANEL_WIDTH }}
            className="fixed z-50 flex flex-col gap-2 rounded-control border border-border bg-popover p-3 text-meta text-popover-foreground shadow-floating"
          >
            {children}
          </div>,
          document.body,
        )}
    </>
  );
}
