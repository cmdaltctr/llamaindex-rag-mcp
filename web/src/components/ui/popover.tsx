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
  className?: string;
}

const EDGE = 8;

/** Where the panel goes: under the trigger, moved left when it would run off the right edge of the screen. */
function placeUnder(button: HTMLElement, width: number): { top: number; left: number; maxHeight: number } {
  const rect = button.getBoundingClientRect();
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE));
  const top = rect.bottom + 4;
  // Keep the whole panel on screen: a tall panel scrolls inside the space below the trigger.
  return { top, left, maxHeight: Math.max(160, window.innerHeight - top - EDGE) };
}

/**
 * A panel that opens under its trigger on click. Escape, a click elsewhere or a
 * second click closes it, and Escape returns focus to the trigger. A scroll or a
 * resize of the page closes it, because a fixed panel would drift from its
 * trigger; a scroll inside the panel does not. The panel is drawn on the page
 * body, so a clipping ancestor cannot cut it off.
 */
export function Popover({ trigger, children, slot = "popover-content", width = 288, className }: PopoverProps) {
  const [position, setPosition] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const open = position !== null;

  useEffect(() => {
    if (!open) return;
    const close = () => setPosition(null);
    const outside = (target: EventTarget | null) =>
      target instanceof Node && !button.current?.contains(target) && !panel.current?.contains(target);
    const onPointerDown = (event: PointerEvent) => {
      if (outside(event.target)) close();
    };
    const onScroll = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Node) || target === document || outside(target)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
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
        onClick: () => setPosition((current) => (current ? null : button.current ? placeUnder(button.current, width) : null)),
      })}
      {position &&
        createPortal(
          <div
            ref={panel}
            id={panelId}
            data-slot={slot}
            style={{ top: position.top, left: position.left, width, maxHeight: position.maxHeight }}
            className={cn("fixed z-50 flex flex-col gap-2 rounded-control border border-border bg-popover p-3 text-meta text-popover-foreground shadow-floating", className)}
          >
            {typeof children === "function" ? children({ close: () => setPosition(null) }) : children}
          </div>,
          document.body,
        )}
    </>
  );
}
