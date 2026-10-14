import { useState, type FormEvent } from "react";
import type { FetchLike } from "../../api/client";
import { registerPlugin } from "../../api/plugins";
import { pluginStatusLabel } from "../../experiments/labels";
import { ErrorNotice } from "../shared/controls";
import { messageOf } from "../shared/labels";

interface PluginRegisterFormProps {
  fetchImpl?: FetchLike;
  onRegistered: () => void;
}

/** Registers an approved manifest and executable. Registration runs no process and installs nothing. */
export function PluginRegisterForm({ fetchImpl, onRegistered }: PluginRegisterFormProps) {
  const [manifestPath, setManifestPath] = useState("");
  const [executablePath, setExecutablePath] = useState("");
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = approved && manifestPath.trim() !== "" && executablePath.trim() !== "" && !busy;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setError(null);
    setDone(null);
    setBusy(true);
    try {
      const state = await registerPlugin({ manifestPath: manifestPath.trim(), executablePath: executablePath.trim(), approved }, { fetchImpl });
      setDone(`Registered ${state.name}: ${pluginStatusLabel(state.status)}. ${state.message}`);
      setApproved(false);
      onRegistered();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel panel--nested" aria-label="Register a plugin" onSubmit={(event) => void submit(event)}>
      <h3 className="type-section-title">Register a plugin</h3>
      <p className="type-meta">
        Use the shipped manifest or one below the workspace plugins folder. The executable must be on the server&apos;s PATH or below that folder.
      </p>
      <div className="form-row">
        <label className="field field--grow">
          <span className="field__label">Manifest path</span>
          <input className="control" dir="ltr" value={manifestPath} onChange={(e) => setManifestPath(e.target.value)} />
        </label>
        <label className="field field--grow">
          <span className="field__label">Executable path</span>
          <input className="control" dir="ltr" value={executablePath} onChange={(e) => setExecutablePath(e.target.value)} />
        </label>
      </div>
      <label className="field-inline">
        <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
        <span>I approve this manifest and executable. Notebooks they open run Python with my permissions.</span>
      </label>
      <div className="button-row">
        <button type="submit" className="button button--tinted" disabled={!ready}>
          Register plugin
        </button>
      </div>
      <ErrorNotice message={error} />
      {done !== null ? <p className="notice notice--success server-text">{done}</p> : null}
    </form>
  );
}
