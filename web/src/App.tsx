import { useEffect, useRef, useState } from "react";
import { renderArea } from "./areas";
import { AppNav } from "./components/AppNav";
import { TopBar } from "./components/TopBar";
import { CanvasFullScreenProvider, useCanvasFullScreen } from "./lib/CanvasFullScreen";
import { PreferencesProvider } from "./lib/PreferencesProvider";
import { RouteProvider, useRoute } from "./lib/RouteProvider";
import { useNavCollapsed } from "./lib/navCollapsed";
import { cn } from "./lib/utils";

function Shell() {
  const { route, navigated } = useRoute();
  const [storedCollapsed, toggleStored] = useNavCollapsed();
  const mainRef = useRef<HTMLElement>(null);
  const { fullScreen, setFullScreen } = useCanvasFullScreen();

  // On a profile canvas the navigation is an icon column whatever the stored
  // choice says. The user can expand it for this visit only: `expandedFor` holds
  // the profile they expanded it on and is never stored.
  const canvasId = route.area === "studio" ? route.profileId : null;
  const onCanvas = canvasId !== null;
  // Full screen ends when the user leaves the canvas.
  useEffect(() => {
    if (!onCanvas) setFullScreen(false);
  }, [onCanvas, setFullScreen]);
  const chromeHidden = onCanvas && fullScreen;
  // Chat collapses the navigation the same way, so the conversation gets the width.
  const collapseKey = canvasId !== null ? `studio:${canvasId}` : route.area === "chat" ? "chat" : null;
  const [expandedFor, setExpandedFor] = useState<string | null>(null);
  if (collapseKey === null && expandedFor !== null) setExpandedFor(null);
  const navCollapsed = collapseKey !== null ? expandedFor !== collapseKey : storedCollapsed;
  const toggleNav =
    collapseKey !== null ? () => setExpandedFor((current) => (current === collapseKey ? null : collapseKey)) : toggleStored;

  // After the user moves to another area, move focus to its heading so
  // screen readers announce it. The first load keeps the browser default.
  useEffect(() => {
    if (!navigated) return;
    const heading = mainRef.current?.querySelector("h1");
    if (heading instanceof HTMLElement) heading.focus();
    else mainRef.current?.focus();
  }, [navigated, route.area]);

  return (
    <div
      className={cn(
        "grid grid-cols-[minmax(0,1fr)]",
        chromeHidden ? "grid-rows-[1fr]" : "grid-rows-[auto_auto_1fr] md:grid-rows-[auto_1fr]",
        onCanvas ? "h-dvh" : "min-h-dvh",
        !chromeHidden && (navCollapsed ? "md:grid-cols-[3.5rem_minmax(0,1fr)]" : "md:grid-cols-[13rem_minmax(0,1fr)]"),
      )}
    >
      {chromeHidden ? null : (
        <>
          <a
            className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-20 focus:rounded-control focus:bg-card focus:px-3 focus:py-2"
            href="#workspace-main"
          >
            Skip to content
          </a>
          <TopBar />
          <AppNav current={route.area} collapsed={navCollapsed} onToggle={toggleNav} />
        </>
      )}
      <main
        id="workspace-main"
        ref={mainRef}
        tabIndex={-1}
        className={cn(
          "flex min-w-0 flex-col outline-none",
          onCanvas ? "min-h-0 overflow-auto lg:overflow-hidden" : "p-4 md:p-6",
        )}
      >
        {renderArea(route)}
      </main>
    </div>
  );
}

/** The shell. It needs `ApiProvider` and `QueryClientProvider` above it, which `main.tsx` supplies. */
export default function App() {
  return (
    <PreferencesProvider>
      <RouteProvider>
        <CanvasFullScreenProvider>
          <Shell />
        </CanvasFullScreenProvider>
      </RouteProvider>
    </PreferencesProvider>
  );
}
