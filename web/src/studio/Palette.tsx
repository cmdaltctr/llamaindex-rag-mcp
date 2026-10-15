import { useId, useState } from "react";
import type { OperationDescriptor } from "../api/pipelines";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

interface PaletteProps {
  operations: readonly OperationDescriptor[] | undefined;
  error: unknown;
  onRetry: () => void;
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
export function Palette({ operations, error, onRetry, onAdd }: PaletteProps) {
  const [query, setQuery] = useState("");
  const idBase = useId();
  const visible = (operations ?? []).filter((operation) => matches(operation, query));

  return (
    <section aria-label="Operation catalogue" className="flex flex-col gap-3 rounded-panel border border-border bg-card p-4">
      <h2 className="text-section-title font-semibold">Operations</h2>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idBase}-search`}>Search operations</Label>
        <Input id={`${idBase}-search`} type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {error !== null && error !== undefined && <ErrorNotice error={error} onRetry={onRetry} />}
      {operations === undefined && !error && <p className="text-meta text-muted-foreground">Loading the catalogue.</p>}
      <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto">
        {visible.map((operation) => {
          const reasonId = `${idBase}-${operation.operation_id}-${operation.version}`;
          return (
            <li key={`${operation.operation_id}@${operation.version}`} className="flex flex-col gap-1">
              <Button
                variant="outline"
                disabled={!operation.available}
                aria-label={`Add ${operation.title} (${operation.operation_id})`}
                aria-describedby={operation.available ? undefined : reasonId}
                onClick={() => onAdd(operation)}
                className="h-auto w-full flex-col items-start gap-0.5 whitespace-normal rounded-control px-2.5 py-1.5 text-start"
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span className="font-medium">{operation.title}</span>
                  <Badge variant="hue">{operation.family}</Badge>
                </span>
                <code className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">{operation.operation_id}</code>
              </Button>
              {!operation.available && (
                <p id={reasonId} className="px-2 text-meta text-muted-foreground">
                  {operation.unavailable_reasons.join(" ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {operations !== undefined && visible.length === 0 && <p className="text-meta text-muted-foreground">No operation matches this search.</p>}
    </section>
  );
}
