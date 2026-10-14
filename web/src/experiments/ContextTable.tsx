import type { FetchLike } from "../api/client";
import { revokeExperiment, type ExperimentEntry } from "../api/experiments";
import { ConfirmAction } from "./ConfirmAction";

interface ContextTableProps {
  entries: ExperimentEntry[];
  fetchImpl?: FetchLike;
  onChanged: () => void;
}

/** Approved experiment contexts with their store backend and index identity. */
export function ContextTable({ entries, fetchImpl, onChanged }: ContextTableProps) {
  if (entries.length === 0) {
    return (
      <div className="empty-state empty-state--compact" data-testid="empty-state">
        <p className="empty-state__title">No experiment workspace is registered</p>
        <p className="type-meta">Register a folder below an approved experiment root to start.</p>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table className="data-table" aria-label="Experiment contexts">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Status</th>
            <th scope="col">Workspace</th>
            <th scope="col">Store</th>
            <th scope="col">Index identity</th>
            <th scope="col">Embedding</th>
            <th scope="col">Permitted</th>
            <th scope="col">Manage</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(({ experiment, identity }) => {
            const name = experiment.name || experiment.context_id;
            return (
              <tr key={experiment.context_id}>
                <td>
                  <span>{name}</span>
                  <br />
                  <span className="type-code">{experiment.context_id}</span>
                </td>
                <td>{experiment.status === "active" ? "Active" : "Revoked"}</td>
                <td className="type-code" dir="ltr">
                  {experiment.workspace}
                </td>
                <td>
                  <span>{identity.store_kind}</span>
                  <br />
                  <span className="type-code" dir="ltr">
                    {identity.store_path}
                  </span>
                </td>
                <td className="type-code">{identity.index_identity}</td>
                <td className="type-code" dir="ltr">
                  {identity.embedding_provider} / {identity.embedding_model}
                </td>
                <td>{experiment.actions.join(", ")}</td>
                <td>
                  {experiment.status === "active" ? (
                    <ConfirmAction
                      label={`Revoke ${name}`}
                      text="Revoke"
                      warning="Revoking stops new runs in this context. A run that already started finishes. Bound credentials stop working. Workspace files are not touched."
                      confirmLabel="Confirm revoke"
                      cancelLabel="Keep context"
                      onConfirm={async () => {
                        await revokeExperiment(experiment.context_id, { fetchImpl });
                        onChanged();
                      }}
                    />
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
