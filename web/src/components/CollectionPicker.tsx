import { ChevronDown, ChevronUp } from "lucide-react";
import { useId, useState } from "react";
import type { CollectionInfo } from "../api/documents";
import { collectionTitle } from "../lib/collectionTitle";
import { plural } from "../lib/labels";
import { cn } from "../lib/utils";
import { CollectionFiles } from "./CollectionFiles";
import { Button } from "./ui/button";

interface CollectionPickerProps {
  /** Names the list for assistive technology, for example "Projects". */
  label: string;
  collections: readonly CollectionInfo[];
  selected: string | null;
  onSelect: (name: string) => void;
  /** Stack the chips in a column, for a side panel. */
  stacked?: boolean;
  /** Add a chevron to each chip that opens the file names of that collection under it. */
  showFiles?: boolean;
}

/** The one way to pick a collection: a chip per collection with its counts. Selection is neutral, never accent. */
export function CollectionPicker({ label, collections, selected, onSelect, stacked = false, showFiles = false }: CollectionPickerProps) {
  const idBase = useId();
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (name: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(name)) next.add(name);
      return next;
    });

  return (
    <ul aria-label={label} className={cn("flex gap-2", stacked ? "flex-col" : "flex-wrap")}>
      {collections.map((collection) => {
        const title = collectionTitle(collection);
        const expanded = showFiles && open.has(collection.name);
        const filesId = `${idBase}-files-${collection.name}`;
        return (
          <li key={collection.name} className="flex min-w-0 flex-col gap-2">
            <div className="flex items-center gap-1">
              <Button
                variant="chip"
                aria-pressed={collection.name === selected}
                className="min-w-0 flex-1 justify-between gap-3"
                onClick={() => onSelect(collection.name)}
              >
                <span className="max-w-[60%] shrink-0 truncate">{title}</span>
                <span className="min-w-0 truncate text-meta font-normal text-muted-foreground">
                  {plural(collection.document_count, "document")}, {plural(collection.chunk_count, "chunk")} · {collection.store.label}
                </span>
              </Button>
              {showFiles ? (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`${expanded ? "Hide" : "Show"} files in ${title}`}
                  aria-expanded={expanded}
                  aria-controls={expanded ? filesId : undefined}
                  onClick={() => toggle(collection.name)}
                >
                  {expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                </Button>
              ) : null}
            </div>
            {expanded ? <CollectionFiles collection={collection.name} title={title} id={filesId} /> : null}
          </li>
        );
      })}
    </ul>
  );
}
