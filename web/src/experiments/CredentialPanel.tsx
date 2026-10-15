import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { BearerScope, ExperimentRecord, IssuedCredential } from "../api/experiments";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Check, SelectField, TextField } from "./fields";
import { contextLabel } from "./labels";
import { useIssueCredential } from "./mutations";
import { OneTimeSecret } from "./OneTimeSecret";
import { Panel } from "./Panel";

const SCOPES: { scope: BearerScope; text: string }[] = [
  { scope: "graph", text: "Save graphs and revisions" },
  { scope: "read", text: "Read the catalogue and runs" },
  { scope: "run", text: "Submit and cancel runs" },
];

/** Issues a bearer credential bound to one active context, for a notebook client. */
export function CredentialPanel({ active }: { active: ExperimentRecord[] }) {
  const issue = useIssueCredential();
  const [contextId, setContextId] = useState("");
  const [label, setLabel] = useState("notebook");
  const [scopes, setScopes] = useState<Record<BearerScope, boolean>>({ graph: true, read: true, run: true });
  const [issued, setIssued] = useState<IssuedCredential | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const chosen = active.find((item) => item.context_id === contextId) ?? active[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen === undefined) return;
    setIssued(null);
    issue.reset();
    const wanted = SCOPES.map((item) => item.scope).filter((scope) => scopes[scope]);
    if (wanted.length === 0) {
      setProblem("Choose at least one scope.");
      return;
    }
    setProblem(null);
    try {
      setIssued(await issue.mutateAsync({ contextId: chosen.context_id, scopes: wanted, label: label.trim() }));
    } catch {
      // The mutation holds the error, which renders below.
    }
  }

  function hide() {
    setIssued(null);
    issue.reset();
  }

  return (
    <Panel title="Notebook credential" description="A bound credential runs graphs only in its context. It cannot read or change the live library. Credentials last until the server stops.">
      {chosen === undefined ? (
        <p className="text-meta text-muted-foreground">Create a sub-experiment first.</p>
      ) : (
        <form aria-label="Issue a credential" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
          <SelectField label="Context" value={chosen.context_id} onChange={setContextId} options={active.map((item) => ({ value: item.context_id, label: contextLabel(item) }))} />
          <TextField label="Label" value={label} maxLength={80} onChange={setLabel} />
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 text-ui font-medium">Scopes</legend>
            {SCOPES.map(({ scope, text }) => (
              <Check key={scope} checked={scopes[scope]} onChange={(checked) => setScopes({ ...scopes, [scope]: checked })}>
                {text}
              </Check>
            ))}
            {problem !== null ? (
              <p role="alert" className="text-meta text-status-error-label">
                {problem}
              </p>
            ) : null}
          </fieldset>
          <div>
            <Button type="submit" disabled={issue.isPending}>
              <KeyRound aria-hidden="true" />
              Issue credential
            </Button>
          </div>
        </form>
      )}
      {issue.isError ? <ErrorNotice error={issue.error} /> : null}
      {issued !== null ? (
        <OneTimeSecret title="Credential token" secret={issued.token} onHide={hide}>
          <p className="text-meta">
            An editor opened from this page connects by itself. For an editor you start yourself, give the token to the notebook in a file with mode 600 named by{" "}
            <code className="font-mono text-code">OMRG_TOKEN_FILE</code>, and set{" "}
            <code className="font-mono text-code">OMRG_EXPERIMENT_CONTEXT={issued.experiment_context}</code>.
          </p>
        </OneTimeSecret>
      ) : null}
    </Panel>
  );
}
