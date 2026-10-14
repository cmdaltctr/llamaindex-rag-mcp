import type { DocumentInfo } from "../../api/documents";
import { availabilityLabel } from "../shared/labels";

interface SourceTableProps {
  collection: string;
  sources: DocumentInfo[];
  onDelete: (source: DocumentInfo) => void;
}

/** Sources of one collection with chunk counts, stable ids and machine-local availability. */
export function SourceTable({ collection, sources, onDelete }: SourceTableProps) {
  if (sources.length === 0) {
    return <p className="type-meta">This collection has no sources.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table" aria-label={`Sources in ${collection}`}>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Stable ID</th>
            <th scope="col">Chunks</th>
            <th scope="col">On this machine</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.source_id ?? `legacy:${source.source}`}>
              <td className="type-code" dir="ltr">
                {source.source}
              </td>
              <td className="type-code" dir="ltr">
                {source.source_id ?? "No stable ID (legacy row)"}
              </td>
              <td>{source.chunks}</td>
              <td>
                <span className="availability" data-orphaned={String(source.orphaned)}>
                  {availabilityLabel(source.orphaned)}
                </span>
              </td>
              <td>
                <button
                  type="button"
                  className="button button--ghost button--small"
                  aria-label={`Delete ${source.source}`}
                  onClick={() => onDelete(source)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
