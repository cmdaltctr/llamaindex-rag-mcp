import { SquareArrowOutUpRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError, ClientRefusal } from "../api/client";
import type { ExperimentRecord } from "../api/experiments";
import { editorTabUrl, editorToken, type PluginState } from "../api/plugins";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { describeError } from "../lib/errors";
import { Check, SelectField, TextField } from "./fields";
import { contextLabel } from "./labels";
import { useOpenEditor } from "./mutations";
import { OneTimeSecret } from "./OneTimeSecret";

interface Opened {
  url: string;
  token: string;
}

interface OpenEditorFormProps {
  plugins: PluginState[];
  active: ExperimentRecord[];
}

/**
 * Asks for consent, calls the open route, then opens the editor in a new tab
 * with `noopener`. The token is shown once on this page for the editor's
 * sign-in page (`response_body_once`); it never goes into the tab address.
 */
export function OpenEditorForm({ plugins, active }: OpenEditorFormProps) {
  const open = useOpenEditor();
  const [pluginName, setPluginName] = useState("");
  const [contextId, setContextId] = useState("");
  const [notebook, setNotebook] = useState("");
  const [consent, setConsent] = useState(false);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const plugin = plugins.find((item) => item.name === pluginName) ?? plugins[0]!;
  const context = active.find((item) => item.context_id === contextId) ?? active[0];
  const ready = consent && context !== undefined && notebook.trim() !== "" && !open.isPending;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || context === undefined) return;
    setRefusal(null);
    setOpened(null);
    open.reset();
    try {
      const response = await open.mutateAsync({ plugin: plugin.name, request: { notebook: notebook.trim(), experimentContext: context.context_id, consent } });
      const token = editorToken(response);
      const url = editorTabUrl(response);
      window.open(url, "_blank", "noopener,noreferrer");
      setOpened({ url, token });
      setConsent(false);
    } catch (failure) {
      // An address or token the page refuses to use carries its own plain-English line. A request failure
      // renders from the mutation; anything else gets the shared friendly line.
      if (failure instanceof ClientRefusal) setRefusal(failure.message);
      else if (!(failure instanceof ApiError)) setRefusal(describeError(failure).message);
    }
  }

  function hide() {
    setOpened(null);
    open.reset();
  }

  if (context === undefined) return <p className="text-meta text-muted-foreground">Create a sub-experiment before you open a notebook.</p>;
  return (
    <>
      <form aria-label="Open a notebook editor" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-3">
          <SelectField label="Plugin" value={plugin.name} onChange={setPluginName} options={plugins.map((item) => ({ value: item.name, label: `${item.display_name ?? item.name} ${item.version ?? ""}`.trim() }))} />
          <SelectField label="Experiment context" value={context.context_id} onChange={setContextId} options={active.map((item) => ({ value: item.context_id, label: contextLabel(item) }))} />
        </div>
        <TextField label="Notebook path" dir="ltr" value={notebook} placeholder="starter_notebook.py" hint="A .py file relative to the experiment workspace." onChange={setNotebook} />
        <Check checked={consent} onChange={setConsent}>
          I trust this notebook. Its Python runs with my filesystem and network permissions.
        </Check>
        <div>
          <Button type="submit" disabled={!ready}>
            <SquareArrowOutUpRight aria-hidden="true" />
            Open notebook editor
          </Button>
        </div>
      </form>
      <p className="text-meta text-muted-foreground">The editor opens in a separate browser tab. This page does not embed it. Notebook cells do not run at startup.</p>
      {refusal !== null ? <AlertNotice message={refusal} /> : null}
      {open.isError && refusal === null ? <ErrorNotice error={open.error} /> : null}
      {opened !== null ? (
        <OneTimeSecret title="Editor access token" secret={opened.token} onHide={hide}>
          <p className="text-meta">Paste it into the editor sign-in page. It is not part of the editor address.</p>
          <p className="text-meta">If your browser blocked the new tab, use this link:</p>
          <a href={opened.url} target="_blank" rel="noopener noreferrer" className="w-fit text-primary-label underline underline-offset-4">
            Open the editor tab again
          </a>
        </OneTimeSecret>
      ) : null}
    </>
  );
}
