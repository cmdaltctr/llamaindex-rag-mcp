import type { CollectionInfo } from "../api/documents";
import { collectionTitle } from "../lib/collectionTitle";
import { plural } from "../lib/labels";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

interface CollectionPickerProps {
  /** Names the list for assistive technology, for example "Projects". */
  label: string;
  collections: readonly CollectionInfo[];
  selected: string | null;
  onSelect: (name: string) => void;
  /** Stack the chips in a column, for a side panel. */
  stacked?: boolean;
}

/** The one way to pick a collection: a chip per collection with its counts. Selection is neutral, never accent. */
export function CollectionPicker({ label, collections, selected, onSelect, stacked = false }: CollectionPickerProps) {
  return (
    <ul aria-label={label} className={cn("flex gap-2", stacked ? "flex-col" : "flex-wrap")}>
      {collections.map((collection) => (
        <li key={collection.name} className="min-w-0">
          <Button
            variant="chip"
            aria-pressed={collection.name === selected}
            className="w-full justify-between gap-3"
            onClick={() => onSelect(collection.name)}
          >
            <span className="truncate">{collectionTitle(collection)}</span>
            <span className="truncate text-meta font-normal text-muted-foreground">
              {plural(collection.document_count, "document")}, {plural(collection.chunk_count, "chunk")} · {collection.store.label}
            </span>
          </Button>
        </li>
      ))}
    </ul>
  );
}
