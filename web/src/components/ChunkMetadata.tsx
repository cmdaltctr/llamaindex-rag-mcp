import { useState } from "react";
import type { ChunkView } from "../api/documents";
import { chunkPosition } from "../lib/labels";
import { Button } from "./ui/button";

/** Stored keys that the Lineage section already shows. */
const LINEAGE_KEYS = new Set([
  "chunk_id",
  "source_id",
  "source_version",
  "source_chunk_index",
  "source_chunk_count",
  "page_label",
]);

/** A value longer than this is cut until the user asks for all of it. */
const CUT_AT = 200;

function valueText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

interface ChunkMetadataProps {
  chunk: ChunkView;
  /** Every chunk a merged citation spans. Shown only when it is more than one. */
  chunkIds?: string[];
  /** False hides the Metadata section, for a chunk whose stored metadata could not be read. */
  showMetadata?: boolean;
}

/**
 * The Lineage and Metadata sections of one stored chunk. The index does not
 * record which keys a chunk got from its source document, so the Metadata
 * section lists what is stored and does not label keys as inherited.
 */
export function ChunkMetadata({
  chunk,
  chunkIds,
  showMetadata = true,
}: ChunkMetadataProps) {
  const keys = Object.keys(chunk.metadata)
    .filter((key) => !LINEAGE_KEYS.has(key))
    .sort();
  const position = `${chunkPosition(chunk.source_chunk_index, chunk.source_chunk_count)}${chunk.page_label !== null ? `, Page ${chunk.page_label}` : ""}`;
  return (
    <>
      <section aria-label="Lineage" className="flex flex-col gap-1">
        <h3 className="text-meta font-semibold">Lineage</h3>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-meta">
          <Row label="Source ID" value={chunk.source_id ?? "None"} mono />
          <Row
            label="Source version"
            value={chunk.source_version ?? "None"}
            mono
          />
          <Row label="Position" value={position} />
          {chunkIds !== undefined && chunkIds.length > 1 ? (
            <Row label="Chunk IDs" value={chunkIds.join(", ")} mono />
          ) : null}
        </dl>
      </section>
      {showMetadata ? (
        <section aria-label="Metadata" className="flex flex-col gap-1">
          <h3 className="text-meta font-semibold">Metadata</h3>
          {keys.length === 0 ? (
            <p className="text-meta text-muted-foreground">
              This chunk has no other metadata.
            </p>
          ) : (
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-meta">
              {keys.map((key) => (
                <MetadataRow
                  key={key}
                  name={key}
                  value={valueText(chunk.metadata[key])}
                />
              ))}
            </dl>
          )}
        </section>
      ) : null}
    </>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        dir={mono ? "ltr" : undefined}
        className={mono ? "font-mono text-code break-all" : "break-words"}
      >
        {value}
      </dd>
    </>
  );
}

function MetadataRow({ name, value }: { name: string; value: string }) {
  const [all, setAll] = useState(false);
  const cut = !all && value.length > CUT_AT;
  return (
    <>
      <dt
        dir="ltr"
        className="font-mono text-code text-muted-foreground break-all"
      >
        {name}
      </dt>
      <dd className="flex flex-col items-start gap-1 break-words whitespace-pre-wrap">
        {cut ? `${value.slice(0, CUT_AT)}…` : value}
        {cut ? (
          <Button
            variant="link"
            size="xs"
            aria-label={`Show all of ${name}`}
            onClick={() => setAll(true)}
          >
            Show all
          </Button>
        ) : null}
      </dd>
    </>
  );
}
