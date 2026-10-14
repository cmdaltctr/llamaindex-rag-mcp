import { useState, type FormEvent } from "react";
import type { FetchLike } from "../api/client";
import { createExperiment, workspacePath, type ExperimentAction } from "../api/experiments";
import { ErrorNotice } from "../views/shared/controls";
import { messageOf } from "../views/shared/labels";
import { contextLabel } from "./labels";

interface RegisterFormProps {
  roots: string[] | undefined;
  fetchImpl?: FetchLike;
  onRegistered: () => void;
}

/** Approves a folder below an approved experiment root as a new experiment context. */
export function RegisterForm({ roots, fetchImpl, onRegistered }: RegisterFormProps) {
  const [root, setRoot] = useState("");
  const [folder, setFolder] = useState("");
  const [name, setName] = useState("");
  const [actions, setActions] = useState<Record<ExperimentAction, boolean>>({ read: true, ingest: true });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chosenRoot = root || roots?.[0] || "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setDone(null);
    const chosen = (Object.keys(actions) as ExperimentAction[]).filter((action) => actions[action]);
    try {
      if (chosen.length === 0) throw new Error("Choose at least one permitted action.");
      const workspace = workspacePath(chosenRoot, folder);
      setBusy(true);
      const created = await createExperiment({ workspace, name: name.trim(), actions: chosen }, { fetchImpl });
      setDone(`Registered ${contextLabel(created.experiment)}. Its store is below ${created.experiment.output_dir}.`);
      setFolder("");
      setName("");
      onRegistered();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="experiments-register">
      <h2 id="experiments-register" className="type-section-title">
        Register an experiment workspace
      </h2>
      {roots === undefined ? <p className="type-meta">Loading approved roots.</p> : null}
      {roots !== undefined && roots.length === 0 ? (
        <p className="type-meta">
          This server has no approved experiment root. Restart it with <code className="type-code">omrg web --experiment-root &lt;directory&gt;</code>, then
          register a folder below that root.
        </p>
      ) : null}
      {roots !== undefined && roots.length > 0 ? (
        <form className="form-row" onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span className="field__label">Approved experiment root</span>
            <select className="control control--select" value={chosenRoot} onChange={(e) => setRoot(e.target.value)}>
              {roots.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="field field--grow">
            <span className="field__label">Folder inside the root</span>
            <input className="control" dir="ltr" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="chunk-size-study" />
          </label>
          <label className="field">
            <span className="field__label">Name</span>
            <input className="control" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <fieldset className="field">
            <legend className="field__label">Permitted actions</legend>
            <label className="field-inline">
              <input type="checkbox" checked={actions.read} onChange={(e) => setActions({ ...actions, read: e.target.checked })} />
              <span>Read and run graphs</span>
            </label>
            <label className="field-inline">
              <input type="checkbox" checked={actions.ingest} onChange={(e) => setActions({ ...actions, ingest: e.target.checked })} />
              <span>Ingest into the experiment store</span>
            </label>
          </fieldset>
          <button type="submit" className="button button--tinted" disabled={busy}>
            Register workspace
          </button>
        </form>
      ) : null}
      <p className="type-meta">
        The folder must already exist. Its store is LanceDB, below the folder&apos;s output directory. Contexts last until the server stops.
      </p>
      <ErrorNotice message={error} />
      {done !== null ? <p className="notice notice--success">{done}</p> : null}
    </section>
  );
}
