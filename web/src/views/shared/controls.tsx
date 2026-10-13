import { useEffect, useId, useRef } from "react";
import type { CollectionInfo } from "../../api/documents";
import { viewById, type ViewId } from "../../lib/views";

/** View heading. Focus moves to it after navigation so screen readers announce the view. */
export function ViewHeader({ id, focusHeading }: { id: ViewId; focusHeading: boolean }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const view = viewById(id);
  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);
  return (
    <header className="view__header">
      <h1 id={`view-${id}-title`} className="text-page-title" ref={headingRef} tabIndex={-1}>
        {view.label}
      </h1>
      <p className="text-meta">{view.summary}</p>
    </header>
  );
}

interface CollectionSelectProps {
  collections: CollectionInfo[] | undefined;
  value: string | null;
  onChange: (name: string) => void;
}

export function CollectionSelect({ collections, value, onChange }: CollectionSelectProps) {
  const id = useId();
  const empty = collections === undefined || collections.length === 0;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        Collection
      </label>
      <select id={id} className="control control--select" value={value ?? ""} disabled={empty} onChange={(e) => onChange(e.target.value)}>
        {empty ? <option value="">{collections === undefined ? "Loading collections" : "No collections"}</option> : null}
        {(collections ?? []).map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

const TRI_STATE = { inherit: null, on: true, off: false } as const;
type TriKey = keyof typeof TRI_STATE;

interface TriStateSelectProps {
  label: string;
  value: boolean | null;
  onChange: (value: boolean | null) => void;
}

/** Inherit, on or off. Inherit sends `null`, so the collection profile decides. */
export function TriStateSelect({ label, value, onChange }: TriStateSelectProps) {
  const id = useId();
  const current: TriKey = value === null ? "inherit" : value ? "on" : "off";
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="control control--select"
        value={current}
        onChange={(e) => onChange(TRI_STATE[e.target.value as TriKey])}
      >
        <option value="inherit">Profile decides</option>
        <option value="on">On</option>
        <option value="off">Off</option>
      </select>
    </div>
  );
}

export function ErrorNotice({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p className="notice notice--error" role="alert">
      {message}
    </p>
  );
}
