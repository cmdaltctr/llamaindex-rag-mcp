import { useEffect, useState } from "react";
import type { FetchLike } from "../api/client";
import { listTemplates, type PipelineTemplate } from "./templates";

interface TemplatePickerProps {
  fetchImpl?: FetchLike;
  /** True when loading a template would discard unsaved draft work. */
  replacesWork: boolean;
  disabled: boolean;
  onStart: (template: PipelineTemplate) => void;
}

type Loaded = { templates: PipelineTemplate[] } | { error: string } | null;

/** Starts a new draft from a server template. The empty graph stays the other start. */
export function TemplatePicker({ fetchImpl, replacesWork, disabled, onStart }: TemplatePickerProps) {
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [chosen, setChosen] = useState<string>("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let live = true;
    listTemplates({ fetchImpl }).then(
      (templates) => live && setLoaded({ templates }),
      (error: unknown) => live && setLoaded({ error: error instanceof Error ? error.message : String(error) }),
    );
    return () => {
      live = false;
    };
  }, [fetchImpl]);

  const templates = loaded !== null && "templates" in loaded ? loaded.templates : [];
  const template = templates.find((item) => item.name === chosen) ?? templates[0];

  function start() {
    if (template === undefined) return;
    if (replacesWork && !confirming) return setConfirming(true);
    setConfirming(false);
    onStart(template);
  }

  return (
    <section className="template-picker" aria-label="Start from template">
      {loaded === null ? <p className="text-meta">Loading templates.</p> : null}
      {loaded !== null && "error" in loaded ? (
        <p className="text-meta">Templates are not available: {loaded.error} Start from an empty graph.</p>
      ) : null}
      {template !== undefined ? (
        <>
          <div className="template-picker__row">
            <label className="field">
              <span className="field__label">Template</span>
              <select className="control control--select" value={template.name} onChange={(e) => setChosen(e.target.value)}>
                {templates.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="button button--tinted" disabled={disabled} onClick={start}>
              Start from template
            </button>
          </div>
          <p className="text-meta">
            {template.description} The template is an editable starting point. Save it as a revision before a run.
          </p>
        </>
      ) : null}
      {confirming ? (
        <div className="template-picker__confirm" role="group" aria-label="Replace the draft">
          <p className="text-meta">Loading a template replaces the unsaved draft. Saved revisions are not changed.</p>
          <button type="button" className="button button--tinted" onClick={start}>
            Replace draft
          </button>
          <button type="button" className="button button--ghost" onClick={() => setConfirming(false)}>
            Keep my draft
          </button>
        </div>
      ) : null}
    </section>
  );
}
