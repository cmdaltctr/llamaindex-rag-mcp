import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { collectionsQuery } from "../api/queries";
import { Badge } from "./ui/badge";

/** The engine pill: the collection count from the shared cache, or offline. */
export function EngineStatus() {
  const { data, isError } = useQuery(collectionsQuery(useApi()));
  if (isError) return <Badge variant="error">Offline</Badge>;
  if (data === undefined) return <Badge variant="neutral">Connecting</Badge>;
  return <Badge variant="success">{`${data.length} ${data.length === 1 ? "collection" : "collections"}`}</Badge>;
}
