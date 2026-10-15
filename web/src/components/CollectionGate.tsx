import type { ReactNode } from "react";
import type { CollectionInfo } from "../api/documents";
import { useActiveCollection } from "../lib/useActiveCollection";
import { ErrorNotice } from "./ErrorNotice";
import { NotFound } from "./NotFound";

interface CollectionGateProps {
  area: "knowledge-base" | "chat";
  /** The collection segment of the route. */
  routeCollection: string | null;
  /** The link text of the not-found state, which leads back to the picker. */
  backLabel: string;
  /** Shown when the route names no collection and none can be opened by default. */
  picker: (collections: readonly CollectionInfo[]) => ReactNode;
  children: (active: CollectionInfo, collections: readonly CollectionInfo[]) => ReactNode;
}

/**
 * Resolves the route's collection against the server list and renders the
 * loading, failure, not-found and picker states every collection-scoped view
 * shares. It renders `children` only for a collection the server lists.
 */
export function CollectionGate({ area, routeCollection, backLabel, picker, children }: CollectionGateProps) {
  const { query, collections, active, redirecting } = useActiveCollection(area, routeCollection);
  const backHref = `#/${area}`;

  if (collections === undefined) {
    if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} backHref={backHref} />;
    return (
      <p role="status" className="text-meta text-muted-foreground">
        Loading collections.
      </p>
    );
  }
  if (redirecting) return null;
  if (routeCollection === null) return <>{picker(collections)}</>;
  if (active === null) return <NotFound what="collection" name={routeCollection} backHref={backHref} backLabel={backLabel} />;
  return <>{children(active, collections)}</>;
}
