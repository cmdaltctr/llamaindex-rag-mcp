import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { boundText, scoreText, stageRanks, type Row } from "../../runs/evidence";
import { maskText } from "../../runs/redact";
import { OpenFullOutput } from "./OutputViewer";

export type OpenChunk = (chunkId: string, collection: string | null) => void;

function str(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

/** The collection a row names, if any. */
export function rowCollection(row: Row): string | null {
  const metadata = row.metadata;
  const fromMeta = typeof metadata === "object" && metadata !== null ? (metadata as Row).collection : null;
  return str(row.collection) ?? str(fromMeta);
}

export function ChunkButton({ row, onOpen }: { row: Row; onOpen: OpenChunk }) {
  const chunkId = str(row.chunk_id);
  if (!chunkId) return <span className="text-meta text-muted-foreground">No chunk id</span>;
  return (
    <Button variant="outline" size="sm" onClick={() => onOpen(chunkId, rowCollection(row))}>
      {`Show full chunk ${chunkId}`}
    </Button>
  );
}

function Score({ row }: { row: Row }) {
  const score = scoreText(row.score, row.score_kind);
  return (
    <span>
      {score.label}
      {score.value !== null && <code className="font-mono text-code">{` ${score.value}`}</code>}
    </span>
  );
}

interface EvidenceRowsProps {
  runId: string;
  name: string;
  rows: Row[];
  total: number;
  /** Every row, when `rows` holds only the first ones. */
  all: Row[];
  onOpen: OpenChunk;
}

/** Ranked rows in their delivered order. Rank is the position; the score keeps its own kind. */
export function EvidenceRows({ runId, name, rows, total, all, onOpen }: EvidenceRowsProps) {
  return (
    <div className="flex flex-col gap-2">
      {total > rows.length && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-meta text-muted-foreground">{`Showing the first ${rows.length} of ${total} rows.`}</p>
          <OpenFullOutput runId={runId} name={name} source={{ value: all }} />
        </div>
      )}
      <Table aria-label={`Ranked rows: ${name}`}>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Rank</TableHead>
            <TableHead scope="col">Score</TableHead>
            <TableHead scope="col">Source</TableHead>
            <TableHead scope="col">Preview</TableHead>
            <TableHead scope="col">Chunk</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => {
            const preview = boundText(maskText(str(row.text) ?? ""));
            const earlier = stageRanks(row);
            return (
              <TableRow key={`${index}-${str(row.chunk_id) ?? ""}`}>
                <TableCell>
                  {index + 1}
                  {earlier.length > 0 && <span className="text-meta text-muted-foreground">{` (${earlier.join(", ")})`}</span>}
                </TableCell>
                <TableCell>
                  <Score row={row} />
                </TableCell>
                <TableCell className="[overflow-wrap:anywhere]">{maskText(str(row.source) ?? "Unknown")}</TableCell>
                <TableCell className="min-w-56 whitespace-normal [overflow-wrap:anywhere]">
                  {preview.text}
                  {preview.truncated && (
                    <span className="flex flex-wrap items-center gap-2 pt-1 text-meta text-muted-foreground">
                      Preview cut at 4 KiB.
                      <OpenFullOutput runId={runId} name={`${name}-row-${index + 1}`} source={{ value: row }} />
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <ChunkButton row={row} onOpen={onOpen} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
