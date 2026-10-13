import type { OperationDescriptor } from "../../api/pipelines";
import type { LoadState } from "../shared/useLoad";

interface RuntimeSectionProps {
  health: LoadState<Record<string, unknown>>;
  session: LoadState<{ kind: string; scopes: string[] }>;
  operations: LoadState<OperationDescriptor[]>;
}

function fact<T>(state: LoadState<T>, show: (data: T) => string): string {
  if (state.data !== undefined) return show(state.data);
  if (state.error !== null) return `Not available: ${state.error}`;
  return "Loading";
}

/** Runtime facts reported by the server: readiness, session scopes and operation availability. */
export function RuntimeSection({ health, session, operations }: RuntimeSectionProps) {
  const unavailable = operations.data?.filter((op) => !op.available) ?? [];
  return (
    <section className="panel" aria-labelledby="settings-runtime">
      <h2 id="settings-runtime" className="text-section-title">
        Runtime
      </h2>
      <dl className="facts">
        <dt>Server</dt>
        <dd>{fact(health, (h) => (h.ready === true ? "Ready" : "Starting or shutting down"))}</dd>
        <dt>Session</dt>
        <dd>{fact(session, (s) => s.kind)}</dd>
        <dt>Scopes</dt>
        <dd>{fact(session, (s) => s.scopes.join(", "))}</dd>
        <dt>Pipeline operations</dt>
        <dd>{fact(operations, (ops) => `${ops.length - unavailable.length} of ${ops.length} available`)}</dd>
      </dl>
      {unavailable.length > 0 ? (
        <ul className="plain-list" aria-label="Unavailable operations">
          {unavailable.map((op) => (
            <li key={op.operation_id}>
              {op.title} <span className="text-code">({op.operation_id})</span>: not available in this runtime
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
