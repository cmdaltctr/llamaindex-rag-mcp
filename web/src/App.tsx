import { useEffect, useRef } from "react";
import { renderArea } from "./areas";
import { AppNav } from "./components/AppNav";
import { TopBar } from "./components/TopBar";
import { PreferencesProvider } from "./lib/PreferencesProvider";
import { RouteProvider, useRoute } from "./lib/RouteProvider";

function Shell() {
  const { route, navigated } = useRoute();
  const mainRef = useRef<HTMLElement>(null);

  // After the user moves to another area, move focus to its heading so
  // screen readers announce it. The first load keeps the browser default.
  useEffect(() => {
    if (!navigated) return;
    const heading = mainRef.current?.querySelector("h1");
    if (heading instanceof HTMLElement) heading.focus();
    else mainRef.current?.focus();
  }, [navigated, route.area]);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] min-h-dvh grid-rows-[auto_auto_1fr] md:grid-cols-[13rem_minmax(0,1fr)] md:grid-rows-[auto_1fr]">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-20 focus:rounded-control focus:bg-card focus:px-3 focus:py-2"
        href="#workspace-main"
      >
        Skip to content
      </a>
      <TopBar />
      <AppNav current={route.area} />
      <main id="workspace-main" ref={mainRef} tabIndex={-1} className="flex min-w-0 flex-col p-4 outline-none md:p-6">
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
        <Shell />
      </RouteProvider>
    </PreferencesProvider>
  );
}
