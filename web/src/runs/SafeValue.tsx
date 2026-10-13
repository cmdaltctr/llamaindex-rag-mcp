import { boundText, MAX_PREVIEW_ROWS } from "./evidence";
import { safeEntry } from "./redact";

const MAX_DEPTH = 4;

function Leaf({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-meta">none</span>;
  if (typeof value === "string") {
    const preview = boundText(value);
    return (
      <span className="safe-value__text">
        {preview.text}
        {preview.truncated && <span className="text-meta"> (preview cut at 4 KiB)</span>}
      </span>
    );
  }
  return <code>{String(value)}</code>;
}

/**
 * Renders JSON as nested definition lists. Values are text nodes only, so
 * stored strings can never become markup. Credential keys show the redacted
 * marker; text values pass through the same masking as the server.
 */
export function SafeValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (typeof value !== "object" || value === null) return <Leaf value={value} />;
  if (depth >= MAX_DEPTH) return <span className="text-meta">(nested value not shown)</span>;
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item] as const) : Object.entries(value);
  if (entries.length === 0) return <span className="text-meta">empty</span>;
  const shown = entries.slice(0, MAX_PREVIEW_ROWS);
  return (
    <dl className="safe-value">
      {shown.map(([key, item]) => (
        <div key={key} className="safe-value__entry">
          <dt>
            <code>{key}</code>
          </dt>
          <dd>
            <SafeValue value={safeEntry(key, item)} depth={depth + 1} />
          </dd>
        </div>
      ))}
      {entries.length > shown.length && <p className="text-meta">{`Showing the first ${shown.length} of ${entries.length} entries.`}</p>}
    </dl>
  );
}
