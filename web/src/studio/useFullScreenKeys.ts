import { useEffect, useRef, type RefObject } from "react";
import { useCanvasFullScreen } from "../lib/CanvasFullScreen";
import { isTextField } from "./FlowSurface";

/** The toolbar button that enters full screen. Focus returns to it on leaving. */
export const FULL_SCREEN_TOGGLE = "fullscreen-toggle";

/**
 * Focus and Escape for the canvas full screen mode. Entering moves focus to the
 * X button. Leaving returns focus to the full screen button. Escape leaves,
 * except while focus is in a text field or a menu is open.
 */
export function useFullScreenKeys(exit: RefObject<HTMLElement | null>): void {
  const { fullScreen, setFullScreen } = useCanvasFullScreen();
  const was = useRef(false);

  useEffect(() => {
    if (fullScreen && !was.current) exit.current?.focus();
    if (!fullScreen && was.current) document.querySelector<HTMLElement>(`[data-slot='${FULL_SCREEN_TOGGLE}']`)?.focus();
    was.current = fullScreen;
  }, [fullScreen, exit]);

  useEffect(() => {
    if (!fullScreen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented || (event.target !== null && isTextField(event.target))) return;
      if (document.querySelector("[role='menu'], [role='listbox']")) return;
      setFullScreen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [fullScreen, setFullScreen]);
}
