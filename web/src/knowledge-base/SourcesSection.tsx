import { useQuery } from "@tanstack/react-query";
import { FileX, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import type { DocumentInfo } from "../api/documents";
import { documentsQuery } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { DeleteDialog, type DeleteTarget } from "./DeleteDialog";
import { SourceTable } from "./SourceTable";

interface SourcesSectionProps {
  collection: string;
  onAdd: () => void;
  onCollectionDeleted: () => void;
}

/** The source table of one collection, with deletion of a source or the whole collection. */
export function SourcesSection({ collection, onAdd, onCollectionDeleted }: SourcesSectionProps) {
  const query = useQuery(documentsQuery(useApi(), collection));
  const [deletion, setDeletion] = useState<DeleteTarget | null>(null);
  const sources: DocumentInfo[] | undefined = query.data;

  return (
    <section aria-labelledby="kb-sources-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="kb-sources-title" className="text-section-title font-semibold">
          Sources in {collection}
        </h2>
        <Button variant="destructive" size="sm" aria-label={`Delete collection ${collection}`} onClick={() => setDeletion({ kind: "collection" })}>
          <Trash2 aria-hidden="true" />
          Delete collection
        </Button>
      </div>
      {sources === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading sources.
          </p>
        )
      ) : sources.length === 0 ? (
        <EmptyState
          icon={FileX}
          message="This project has no sources yet."
          action={
            <Button onClick={onAdd}>
              <Plus aria-hidden="true" />
              Add sources
            </Button>
          }
        />
      ) : (
        <SourceTable collection={collection} sources={sources} onDelete={(source) => setDeletion({ kind: "source", source })} />
      )}
      {deletion !== null ? (
        <DeleteDialog
          key={JSON.stringify(deletion)}
          collection={collection}
          target={deletion}
          onClose={() => setDeletion(null)}
          onCollectionDeleted={onCollectionDeleted}
        />
      ) : null}
    </section>
  );
}
