import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface CanvasFullScreenState {
  /** True while the Studio canvas fills the window. It is never stored. */
  fullScreen: boolean;
  setFullScreen: (on: boolean) => void;
}

const CanvasFullScreenContext = createContext<CanvasFullScreenState>({ fullScreen: false, setFullScreen: () => undefined });

/** Holds the full screen flag of the canvas, so the shell can hide its chrome while the canvas fills the window. */
export function CanvasFullScreenProvider({ children }: { children: ReactNode }) {
  const [fullScreen, setFullScreen] = useState(false);
  const value = useMemo(() => ({ fullScreen, setFullScreen }), [fullScreen]);
  return <CanvasFullScreenContext.Provider value={value}>{children}</CanvasFullScreenContext.Provider>;
}

export function useCanvasFullScreen(): CanvasFullScreenState {
  return useContext(CanvasFullScreenContext);
}
