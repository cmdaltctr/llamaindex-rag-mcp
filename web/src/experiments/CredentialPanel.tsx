import { useState, type FormEvent } from "react";
import type { FetchLike } from "../api/client";
import { issueBoundCredential, type BearerScope, type ExperimentRecord, type IssuedCredential } from "../api/experiments";
import { ErrorNotice } from "../views/shared/controls";
import { messageOf } from "../views/shared/labels";
import { contextLabel } from "./labels";
import { OneTimeSecret } from "./OneTimeSecret";

const SCOPES: { scope: BearerScope; text: string }[] = [
  { scope: "graph", text: "Save graphs and revisions" },
  { scope: "read", text: "Read the catalogue and runs" },
  { scope: "run", text: "Submit and cancel runs" },
];

interface CredentialPanelProps {
  active: ExperimentRecord[];
  fetchImpl?: FetchLike;
}

/** Issues a bearer credential bound to one active context, for a notebook client. */
export function CredentialPanel({ active, fetchImpl }: CredentialPanelProps) {
  const [contextId, setContextId] = useState("");
  const [label, setLabel] = useState("notebook");
  const [scopes, setScopes] = useState<Record<BearerScope, boolean>>({ graph: true, read: true, run: true });
  const [issued, setIssued] = useState<IssuedCredential | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chosen = active.find((item) => item.context_id === contextId) ?? active[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen === undefined) return;
    setError(null);
    setIssued(null);
    const wanted = SCOPES.map((item) => item.scope).filter((scope) => scopes[scope]);
    try {
      if (wanted.length === 0) throw new Error("Choose at least one scope.");
      setBusy(true);
      setIssued(await issueBoundCredential(chosen.context_id, wanted, label.trim(), { fetchImpl }));
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="experiments-credential">
      <h2 id="experiments-credential" className="text-section-title">
        Notebook credential
      </h2>
      <p className="text-meta">
        A bound credential runs graphs only in its context. It cannot read or change the live library. Credentials last until the server stops.
      </p>
      {chosen === undefined ? (
        <p className="text-meta">Register an experiment workspace first.</p>
      ) : (
        <form className="form-row" onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span className="field__label">Context</span>
            <select className="control control--select" value={chosen.context_id} onChange={(e) => setContextId(e.target.value)}>
              {active.map((item) => (
                <option key={item.context_id} value={item.context_id}>
                  {contextLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Label</span>
            <input className="control" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <fieldset className="field">
            <legend className="field__label">Scopes</legend>
            {SCOPES.map(({ scope, text }) => (
              <label key={scope} className="field-inline">
                <input type="checkbox" checked={scopes[scope]} onChange={(e) => setScopes({ ...scopes, [scope]: e.target.checked })} />
                <span>{text}</span>
              </label>
            ))}
          </fieldset>
          <button type="submit" className="button button--tinted" disabled={busy}>
            Issue credential
          </button>
        </form>
      )}
      <ErrorNotice message={error} />
      {issued !== null ? (
        <OneTimeSecret title="Credential token" secret={issued.token} onHide={() => setIssued(null)}>
          <p className="text-meta">
            An editor opened from this page connects by itself. For an editor you start yourself, give the token to the
            notebook in a file with mode 600 named by <code className="text-code">OMRG_TOKEN_FILE</code>, and set{" "}
            <code className="text-code">OMRG_EXPERIMENT_CONTEXT={issued.experiment_context}</code>.
          </p>
        </OneTimeSecret>
      ) : null}
    </section>
  );
}
