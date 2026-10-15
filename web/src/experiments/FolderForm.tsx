import { FolderPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "../components/ui/button";
import { SelectField, TextField } from "./fields";
import { useCreateFolder } from "./mutations";
import { Panel } from "./Panel";
import { refusalMessage } from "./refusals";

/** Creates a main folder below an approved experiment root. The server validates the path. */
export function FolderForm({ roots }: { roots: readonly string[] }) {
  const create = useCreateFolder();
  const [root, setRoot] = useState(roots[0] ?? "");
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const several = roots.length > 1;
  const chosenRoot = roots.includes(root) ? root : (roots[0] ?? "");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    const trimmed = path.trim();
    if (trimmed === "") {
      setError("Enter a folder name.");
      return;
    }
    setError(null);
    try {
      const folder = await create.mutateAsync({ path: trimmed, root: several ? chosenRoot : null });
      setDone(`Created folder ${folder.path}.`);
      setPath("");
    } catch (failure) {
      setError(refusalMessage(failure));
    }
  }

  return (
    <Panel title="Create a folder" description="A main folder holds the sub-experiments of one study.">
      <form aria-label="Create a folder" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        {several ? <SelectField label="Experiment root" value={chosenRoot} onChange={setRoot} options={roots.map((item) => ({ value: item, label: item }))} ltr /> : null}
        <TextField
          label="Folder name"
          dir="ltr"
          value={path}
          placeholder="hybrid-search"
          hint="Use a / for a nested folder, for example hybrid-search/run-1. A path has at most four levels."
          error={error}
          onChange={(value) => {
            setPath(value);
            setError(null);
          }}
        />
        <div>
          <Button type="submit" disabled={create.isPending}>
            <FolderPlus aria-hidden="true" />
            Create folder
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
