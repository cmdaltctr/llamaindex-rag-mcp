import { useId, useState, type FormEvent } from "react";
import type { FetchLike } from "../api/client";
import type { ExperimentRecord } from "../api/experiments";
import { editorTabUrl, editorToken, openEditor, type PluginState } from "../api/plugins";
import { ErrorNotice } from "../views/shared/controls";
import { messageOf } from "../views/shared/labels";
import { contextLabel } from "./labels";
import { OneTimeSecret } from "./OneTimeSecret";

interface OpenEditorFormProps {
  plugins: PluginState[];
  active: ExperimentRecord[];
  fetchImpl?: FetchLike;
  onOpened: () => void;
}

interface Opened {
  url: string;
  token: string;
}

/**
 * Asks for consent, calls the open route, then opens the editor in a new tab
 * with `noopener`. The token is shown once on this page for the editor's
 * sign-in page (`response_body_once`); it never goes into the tab address.
 */
export function OpenEditorForm({ plugins, active, fetchImpl, onOpened }: OpenEditorFormProps) {
  const hintId = useId();
  const [pluginName, setPluginName] = useState("");
  const [contextId, setContextId] = useState("");
  const [notebook, setNotebook] = useState("");
  const [consent, setConsent] = useState(false);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const plugin = plugins.find((item) => item.name === pluginName) ?? plugins[0]!;
  const context = active.find((item) => item.context_id === contextId) ?? active[0];
  const ready = consent && context !== undefined && notebook.trim() !== "" && !busy;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || context === undefined) return;
    setError(null);
    setOpened(null);
    setBusy(true);
    try {
      const response = await openEditor(plugin.name, { notebook: notebook.trim(), experimentContext: context.context_id, consent }, { fetchImpl });
      onOpened();
      const token = editorToken(response);
      const url = editorTabUrl(response);
      window.open(url, "_blank", "noopener,noreferrer");
      setOpened({ url, token });
      setConsent(false);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  if (context === undefined) return <p className="type-meta">Register an experiment workspace before you open a notebook.</p>;
  return (
    <>
      <form className="form-row" onSubmit={(event) => void submit(event)}>
        <label className="field">
          <span className="field__label">Plugin</span>
          <select className="control control--select" value={plugin.name} onChange={(e) => setPluginName(e.target.value)}>
            {plugins.map((item) => (
              <option key={item.name} value={item.name}>
                {item.display_name ?? item.name} {item.version ?? ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">Experiment context</span>
          <select className="control control--select" value={context.context_id} onChange={(e) => setContextId(e.target.value)}>
            {active.map((item) => (
              <option key={item.context_id} value={item.context_id}>
                {contextLabel(item)}
              </option>
            ))}
          </select>
        </label>
        <div className="field field--grow">
          <label className="field">
            <span className="field__label">Notebook path</span>
            <input
              className="control"
              dir="ltr"
              value={notebook}
              placeholder="starter_notebook.py"
              aria-describedby={hintId}
              onChange={(e) => setNotebook(e.target.value)}
            />
          </label>
          <span id={hintId} className="field__hint">
            A .py file relative to the experiment workspace.
          </span>
        </div>
        <label className="field-inline consent">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>I trust this notebook. Its Python runs with my filesystem and network permissions.</span>
        </label>
        <button type="submit" className="button button--tinted" disabled={!ready}>
          Open notebook editor
        </button>
      </form>
      <p className="type-meta">The editor opens in a separate browser tab. This page does not embed it. Notebook cells do not run at startup.</p>
      <ErrorNotice message={error} />
      {opened !== null ? (
        <OneTimeSecret title="Editor access token" secret={opened.token} onHide={() => setOpened(null)}>
          <p className="type-meta">Paste it into the editor sign-in page. It is not part of the editor address.</p>
          <p className="type-meta">If your browser blocked the new tab, use this link:</p>
          <a href={opened.url} target="_blank" rel="noopener noreferrer">
            Open the editor tab again
          </a>
        </OneTimeSecret>
      ) : null}
    </>
  );
}
