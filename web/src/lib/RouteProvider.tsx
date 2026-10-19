import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { formatRoute, parseRoute, type Route } from "./routes";

interface RouteState {
  route: Route;
  /** True once the user has moved to another area, so the shell can move focus. */
  navigated: boolean;
  /** Pushes a history entry, or replaces the current one. */
  navigate: (route: Route, options?: { replace?: boolean }) => void;
}

const RouteContext = createContext<RouteState | null>(null);

/** Reads the hash and rewrites one that is not canonical (unknown, empty) to its canonical form. */
function readRoute(): Route {
  const route = parseRoute(window.location.hash);
  const canonical = formatRoute(route);
  if (window.location.hash !== canonical) window.history.replaceState(null, "", canonical);
  return route;
}

/** The address bar hash is the only source of location. */
export function RouteProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>(readRoute);
  const [navigated, setNavigated] = useState(false);

  useEffect(() => {
    function sync() {
      setRoute(readRoute());
      setNavigated(true);
    }
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  const navigate = useCallback((next: Route, options: { replace?: boolean } = {}) => {
    const hash = formatRoute(next);
    if (window.location.hash !== hash) {
      if (options.replace) window.history.replaceState(null, "", hash);
      else window.history.pushState(null, "", hash);
    }
    setRoute(next);
    setNavigated(true);
  }, []);

  const value = useMemo(() => ({ route, navigated, navigate }), [route, navigated, navigate]);
  return <RouteContext.Provider value={value}>{children}</RouteContext.Provider>;
}

export function useRoute(): RouteState {
  const state = useContext(RouteContext);
  if (state === null) throw new Error("useRoute must be used inside a RouteProvider.");
  return state;
}
