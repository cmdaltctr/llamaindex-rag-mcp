import { useId, useState } from "react";
import type { OperationDescriptor } from "../api/pipelines";

interface PaletteProps {
  operations: readonly OperationDescriptor[] | null;
  error: string | null;
  onAdd: (operation: OperationDescriptor) => void;
}

function matches(operation: OperationDescriptor, query: string): boolean {
  const text = `${operation.title} ${operation.operation_id} ${operation.family} ${operation.description}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.includes(word));
}

/** Searchable operation catalogue. Unavailable operations stay listed, disabled, with the host's reasons. */
export function Palette({ operations, error, onAdd }: PaletteProps) {
  const [query, setQuery] = useState("");
  const headingId = useId();
  const visible = (operations ?? []).filter((operation) => matches(operation, query));

  return (
    <section className="canvas-panel palette" aria-label="Operation catalogue">
      <h2 className="type-section-title">
        Operations
      </h2>
      <label className="field">
        <span className="field__label">Search operations</span>
        <input className="control" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      {error && (
        <p className="type-meta canvas-error" role="alert">
          {error}
        </p>
      )}
      {operations === null && !error && <p className="type-meta">Loading the catalogue.</p>}
      <ul className="palette__list">
        {visible.map((operation) => {
          const reasonId = `${headingId}-${operation.operation_id}-${operation.version}`;
          return (
            <li key={`${operation.operation_id}@${operation.version}`} className="palette__item">
              <button
                type="button"
                className="palette__button"
                disabled={!operation.available}
                aria-label={`Add ${operation.title} (${operation.operation_id})`}
                aria-describedby={operation.available ? undefined : reasonId}
                onClick={() => onAdd(operation)}
              >
                <span className="palette__title">{operation.title}</span>
                <code className="palette__id">{operation.operation_id}</code>
              </button>
              {!operation.available && (
                <p id={reasonId} className="type-meta palette__reason">
                  {operation.unavailable_reasons.join(" ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {operations !== null && visible.length === 0 && <p className="type-meta">No operation matches this search.</p>}
    </section>
  );
}
