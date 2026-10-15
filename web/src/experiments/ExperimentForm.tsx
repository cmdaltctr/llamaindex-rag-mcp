import { FlaskConical } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { ExperimentAction } from "../api/experiments";
import { Button } from "../components/ui/button";
import { Check, SelectField, TextField } from "./fields";
import { useCreateSubExperiment } from "./mutations";
import { Panel } from "./Panel";
import { refusalMessage } from "./refusals";

export interface FolderOption {
  root: string;
  /** Path below the root, such as `hybrid-search`. */
  path: string;
}

const MAX_FACTORS = 8;

/** The declared factors in a comma-separated entry: trimmed, without blanks or repeats. */
export function parseFactors(text: string): string[] {
  return [...new Set(text.split(",").map((part) => part.trim()).filter((part) => part !== ""))];
}

interface ExperimentFormProps {
  folders: readonly FolderOption[];
  sendRoot: boolean;
}

/** Creates a sub-experiment: a folder inside a main folder, registered as an experiment context. */
export function ExperimentForm({ folders, sendRoot }: ExperimentFormProps) {
  const create = useCreateSubExperiment();
  const [folderKey, setFolderKey] = useState("");
  const [name, setName] = useState("");
  const [factors, setFactors] = useState("");
  const [actions, setActions] = useState<Record<ExperimentAction, boolean>>({ read: true, ingest: true });
  const [problems, setProblems] = useState<{ name?: string; factors?: string; actions?: string }>({});
  const [done, setDone] = useState<string | null>(null);
  const keyOf = (folder: FolderOption) => `${folder.root}\n${folder.path}`;
  const chosen = folders.find((folder) => keyOf(folder) === folderKey) ?? folders[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    const declared = parseFactors(factors);
    const permitted = (Object.keys(actions) as ExperimentAction[]).filter((action) => actions[action]);
    const found = {
      ...(name.trim() === "" ? { name: "Enter a name." } : {}),
      ...(declared.length > MAX_FACTORS ? { factors: `Declare at most eight factors.` } : {}),
      ...(permitted.length === 0 ? { actions: "Choose at least one permitted action." } : {}),
    };
    setProblems(found);
    if (chosen === undefined || Object.keys(found).length > 0) return;
    try {
      const created = await create.mutateAsync({ root: chosen.root, parent: chosen.path, name: name.trim(), sendRoot, actions: permitted, factors: declared });
      setDone(`Created ${created.experiment.name || created.experiment.context_id} in ${chosen.path}.`);
      setName("");
      setFactors("");
    } catch (failure) {
      setProblems({ name: refusalMessage(failure) });
    }
  }

  return (
    <Panel title="Create a sub-experiment" description="Makes a folder inside a main folder and approves it as an experiment context.">
      <form aria-label="Create a sub-experiment" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        {chosen === undefined ? (
          <p className="text-meta text-muted-foreground">Create a folder first. A sub-experiment lives inside a main folder.</p>
        ) : (
          <>
            <SelectField
              label="Folder"
              value={keyOf(chosen)}
              onChange={setFolderKey}
              options={folders.map((folder) => ({ value: keyOf(folder), label: sendRoot ? `${folder.path} (${folder.root})` : folder.path }))}
              ltr
            />
            <TextField label="Name" value={name} maxLength={80} error={problems.name} hint="Also the folder name. Letters, numbers, dots, dashes and underscores." onChange={setName} />
            <TextField
              label="Declared factors"
              value={factors}
              error={problems.factors}
              placeholder="chunk-size, reranker"
              hint="The settings this experiment varies, separated by commas. At most eight."
              onChange={setFactors}
            />
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1.5 text-ui font-medium">Permitted actions</legend>
              <Check checked={actions.read} onChange={(read) => setActions({ ...actions, read })}>
                Read and run graphs
              </Check>
              <Check checked={actions.ingest} onChange={(ingest) => setActions({ ...actions, ingest })}>
                Ingest into the experiment store
              </Check>
              {problems.actions ? (
                <p role="alert" className="text-meta text-status-error-label">
                  {problems.actions}
                </p>
              ) : null}
            </fieldset>
          </>
        )}
        <div>
          <Button type="submit" disabled={chosen === undefined || create.isPending}>
            <FlaskConical aria-hidden="true" />
            Create sub-experiment
          </Button>
        </div>
        {done !== null ? (
          <p role="status" className="text-meta text-muted-foreground">
            {done}
          </p>
        ) : null}
      </form>
    </Panel>
  );
}
