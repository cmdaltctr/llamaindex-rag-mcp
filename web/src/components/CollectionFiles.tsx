import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { documentsQuery } from "../api/queries";
import { ErrorNotice } from "./ErrorNotice";

interface CollectionFilesProps {
  /** Collection name used for the request. */
  collection: string;
  /** Name shown to the reader and to assistive technology. */
  title: string;
  id: string;
}

/** The last segment of a stored source path, for either path separator. */
function fileName(source: string): string {
  return source.split(/[\\/]/).filter(Boolean).pop() ?? source;
}

/** File names of one collection, one per source. Chunk counts stay out of this list. */
export function CollectionFiles({ collection, title, id }: CollectionFilesProps) {
  const query = useQuery(documentsQuery(useApi(), collection));
  const sources = query.data;

  if (sources === undefined) {
    return query.isError ? (
      <div id={id}>
        <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
      </div>
    ) : (
      <p id={id} role="status" className="px-3 text-meta text-muted-foreground">
        Loading files.
      </p>
    );
  }
  if (sources.length === 0) {
    return (
      <p id={id} className="px-3 text-meta text-muted-foreground">
        No files in this knowledge base.
      </p>
    );
  }
  return (
    <ul id={id} aria-label={`Files in ${title}`} className="flex max-h-56 flex-col gap-1 overflow-y-auto px-3 text-meta text-muted-foreground">
      {sources.map((source) => (
        <li key={source.source_id ?? `legacy:${source.source}`} title={source.source} dir="ltr" className="shrink-0 truncate">
          {fileName(source.source)}
        </li>
      ))}
    </ul>
  );
}
