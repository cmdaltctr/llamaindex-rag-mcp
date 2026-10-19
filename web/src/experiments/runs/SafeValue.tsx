import { boundText, MAX_PREVIEW_ROWS } from "../../runs/evidence";
import { safeEntry } from "../../runs/redact";
import { MAX_DEPTH } from "./cut";

function Leaf({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">none</span>;
  if (typeof value === "string") {
    const preview = boundText(value);
    return (
      <span className="[overflow-wrap:anywhere]">
        {preview.text}
        {preview.truncated && <span className="text-muted-foreground"> (preview cut at 4 KiB)</span>}
      </span>
    );
  }
  return <code className="font-mono text-code [overflow-wrap:anywhere]">{String(value)}</code>;
}

/**
 * Renders JSON as nested definition lists. Values are text nodes only, so
 * stored strings can never become markup. Credential keys show the redacted
 * marker; text values pass through the same masking as the server.
 */
export function SafeValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (typeof value !== "object" || value === null) return <Leaf value={value} />;
  if (depth >= MAX_DEPTH) return <span className="text-muted-foreground">(nested value not shown)</span>;
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item] as const) : Object.entries(value);
  if (entries.length === 0) return <span className="text-muted-foreground">empty</span>;
  const shown = entries.slice(0, MAX_PREVIEW_ROWS);
  return (
    <dl className="flex flex-col gap-1 text-meta">
      {shown.map(([key, item]) => (
        <div key={key} className="grid grid-cols-1 gap-x-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
          <dt>
            <code className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">{key}</code>
          </dt>
          <dd className="min-w-0">
            <SafeValue value={safeEntry(key, item)} depth={depth + 1} />
          </dd>
        </div>
      ))}
      {entries.length > shown.length && <p className="text-muted-foreground">{`Showing the first ${shown.length} of ${entries.length} entries.`}</p>}
    </dl>
  );
}
