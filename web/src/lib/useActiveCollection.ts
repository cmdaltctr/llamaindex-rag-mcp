import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useApi } from "../api/ApiProvider";
import { collectionsQuery } from "../api/queries";
import { usePreferences } from "./PreferencesProvider";
import { useRoute } from "./RouteProvider";

/**
 * Resolves the collection a Knowledge Base or Chat route names against the
 * server's list. The route is the only source of the active collection; the
 * stored last-used collection is a default for a route without one, written
 * when a collection opens and dropped once the server no longer lists it.
 */
export function useActiveCollection(area: "knowledge-base" | "chat", routeCollection: string | null) {
  const api = useApi();
  const { navigate } = useRoute();
  const { preferences, setLastCollection } = usePreferences();
  const query = useQuery(collectionsQuery(api));
  const list = query.data;
  const stored = preferences.lastCollection;

  const remembered = list !== undefined && stored !== null && list.some((c) => c.name === stored) ? stored : null;
  const active = list?.find((c) => c.name === routeCollection) ?? null;
  const redirecting = routeCollection === null && remembered !== null;

  useEffect(() => {
    if (list === undefined) return;
    if (redirecting && remembered !== null) navigate(area === "chat" ? { area, collection: remembered, chatId: null } : { area, collection: remembered }, { replace: true });
    else if (stored !== null && remembered === null) setLastCollection(null);
    else if (active !== null && stored !== active.name) setLastCollection(active.name);
  }, [list, redirecting, remembered, stored, active, area, navigate, setLastCollection]);

  return { query, collections: list, active, redirecting };
}
