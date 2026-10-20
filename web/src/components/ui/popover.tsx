import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils";

/** What the trigger element must spread onto itself. */
export interface PopoverTriggerProps {
  ref: Ref<HTMLButtonElement>;
  "aria-expanded": boolean;
  "aria-controls": string | undefined;
  onClick: () => void;
}

interface PopoverProps {
  trigger: (props: PopoverTriggerProps) => ReactNode;
  /** The content, or a function that gets `close` so the content can close the panel. */
  children: ReactNode | ((api: { close: () => void }) => ReactNode);
  /** The `data-slot` of the panel. */
  slot?: string;
  width?: number;
  /** Where the panel opens. `above` suits a trigger at the bottom of the screen; it flips below when there is more room there. */
  placement?: "below" | "above";
  className?: string;
}

interface Position {
  /** Set when the panel opens below the trigger. */
  top?: number;
  /** Set when the panel opens above the trigger. */
  bottom?: number;
  left: number;
  maxHeight: number;
}

const EDGE = 8;

/** Where the panel goes: under (or above) the trigger, moved left when it would run off the right edge of the screen. */
function place(button: HTMLElement, width: number, placement: "below" | "above"): Position {
  const rect = button.getBoundingClientRect();
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE));
  const roomAbove = rect.top - 4 - EDGE;
  const roomBelow = window.innerHeight - rect.bottom - 4 - EDGE;
  // `above` flips below when the trigger sits near the top, for example in the small-screen navigation.
  if (placement === "above" && roomAbove >= roomBelow) {
    return { bottom: window.innerHeight - rect.top + 4, left, maxHeight: Math.max(0, roomAbove) };
  }
  const top = rect.bottom + 4;
  // Keep the whole panel on screen: a tall panel scrolls inside the space below the trigger.
  return { top, left, maxHeight: Math.max(0, window.innerHeight - top - EDGE) };
}

/**
 * A panel that opens under its trigger on click. Escape, a click elsewhere or a
 * second click closes it, and Escape returns focus to the trigger. A scroll or a
 * resize of the page closes it, because a fixed panel would drift from its
 * trigger; a scroll inside the panel does not. The panel is drawn on the page
 * body, so a clipping ancestor cannot cut it off.
 */
export function Popover({ trigger, children, slot = "popover-content", width = 288, placement = "below", className }: PopoverProps) {
  const [position, setPosition] = useState<Position | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const open = position !== null;

  useEffect(() => {
    if (!open) return;
    const close = () => setPosition(null);
    // A select list opened from the panel is drawn on the page body too. It counts as inside the panel.
    const inLayer = (target: EventTarget | null) => target instanceof Element && target.closest('[data-slot="select-content"]') !== null;
    const outside = (target: EventTarget | null) =>
      target instanceof Node && !button.current?.contains(target) && !panel.current?.contains(target) && !inLayer(target);
    const onPointerDown = (event: PointerEvent) => {
      if (outside(event.target)) close();
    };
    const onScroll = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Node) || target === document || outside(target)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      // Escape in an open select list closes that list only.
      if (event.key !== "Escape" || inLayer(event.target)) return;
      close();
      button.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  return (
    <>
      {trigger({
        ref: button,
        "aria-expanded": open,
        "aria-controls": open ? panelId : undefined,
        onClick: () => setPosition((current) => (current ? null : button.current ? place(button.current, width, placement) : null)),
      })}
      {position &&
        createPortal(
          <div
            ref={panel}
            id={panelId}
            data-slot={slot}
            style={{ top: position.top, bottom: position.bottom, left: position.left, width, maxHeight: position.maxHeight }}
            className={cn("fixed z-50 flex flex-col gap-2 overflow-y-auto rounded-control border border-border bg-popover p-3 text-meta text-popover-foreground shadow-floating", className)}
          >
            {typeof children === "function" ? children({ close: () => setPosition(null) }) : children}
          </div>,
          document.body,
        )}
    </>
  );
}
