import { boundText, scoreText, stageRanks, type Row } from "./evidence";
import { maskText } from "./redact";

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
  if (!chunkId) return <span className="text-meta">No chunk id</span>;
  return (
    <button type="button" className="button button--ghost button--small" onClick={() => onOpen(chunkId, rowCollection(row))}>
      {`Show full chunk ${chunkId}`}
    </button>
  );
}

function Score({ row }: { row: Row }) {
  const score = scoreText(row.score, row.score_kind);
  return (
    <span>
      {score.label}
      {score.value !== null && <code>{` ${score.value}`}</code>}
    </span>
  );
}

interface EvidenceRowsProps {
  name: string;
  rows: Row[];
  total: number;
  onOpen: OpenChunk;
}

/** Ranked rows in their delivered order. Rank is the position; the score keeps its own kind. */
export function EvidenceRows({ name, rows, total, onOpen }: EvidenceRowsProps) {
  return (
    <div className="evidence-rows">
      {total > rows.length && <p className="text-meta">{`Showing the first ${rows.length} of ${total} rows.`}</p>}
      <table className="evidence-table" aria-label={`Ranked rows: ${name}`}>
        <thead>
          <tr>
            <th scope="col">Rank</th>
            <th scope="col">Score</th>
            <th scope="col">Source</th>
            <th scope="col">Preview</th>
            <th scope="col">Chunk</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const preview = boundText(maskText(str(row.text) ?? ""));
            const earlier = stageRanks(row);
            return (
              <tr key={`${index}-${str(row.chunk_id) ?? ""}`}>
                <td>
                  {index + 1}
                  {earlier.length > 0 && <span className="text-meta">{` (${earlier.join(", ")})`}</span>}
                </td>
                <td>
                  <Score row={row} />
                </td>
                <td className="evidence-table__source">{maskText(str(row.source) ?? "Unknown")}</td>
                <td className="evidence-table__text">
                  {preview.text}
                  {preview.truncated && <span className="text-meta"> Preview cut at 4 KiB.</span>}
                </td>
                <td>
                  <ChunkButton row={row} onOpen={onOpen} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
