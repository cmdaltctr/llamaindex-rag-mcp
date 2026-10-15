import { useQuery } from "@tanstack/react-query";
import { FolderPlus } from "lucide-react";
import { useApi } from "../api/ApiProvider";
import { collectionsQuery } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { StoreBadge } from "../components/StoreBadge";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { collectionTitle } from "../lib/collectionTitle";
import { plural } from "../lib/labels";
import { formatRoute } from "../lib/routes";
import { areaById } from "../lib/views";

/** The landing view: every collection as a project card that opens its Knowledge Base. */
export function HomeView() {
  const query = useQuery(collectionsQuery(useApi()));
  const collections = query.data;

  return (
    <section>
      <PageHeader title="Home" summary={areaById("home").summary} />
      {collections === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading projects.
          </p>
        )
      ) : collections.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          message="There are no projects yet, because nothing has been ingested into a collection."
          action={
            <Button asChild>
              <a href={formatRoute({ area: "knowledge-base", collection: null })}>Start an ingest</a>
            </Button>
          }
        />
      ) : (
        <ul aria-label="Projects" className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {collections.map((collection) => (
            <li key={collection.name} className="min-w-0">
              <a
                href={formatRoute({ area: "knowledge-base", collection: collection.name })}
                className="group block rounded-panel"
              >
                <Card className="transition-colors duration-150 group-hover:border-border-hover">
                  <CardHeader>
                    <CardTitle className="break-words">{collectionTitle(collection)}</CardTitle>
                    <CardDescription>
                      {plural(collection.document_count, "document")}, {plural(collection.chunk_count, "chunk")}
                    </CardDescription>
                    <span className="font-mono text-meta text-muted-foreground break-all">Collection name: {collection.name}</span>
                  </CardHeader>
                  <CardContent className="flex-row flex-wrap items-center gap-x-3 gap-y-1">
                    {collection.profile !== null ? <Badge variant="hue">{collection.profile}</Badge> : <Badge variant="neutral">No profile</Badge>}
                    <StoreBadge store={collection.store} />
                  </CardContent>
                </Card>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
