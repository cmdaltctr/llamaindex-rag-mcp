import { Pencil } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { CollectionInfo } from "../api/documents";
import { useSetDisplayName } from "../api/mutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { collectionTitle, displayNameProblem } from "../lib/collectionTitle";

/**
 * The project title with a pencil that edits its display name in place, and the
 * real collection name in grey underneath. The display name is only a label;
 * MCP, CLI and API calls use the collection name, so it always stays visible.
 * Enter saves, Escape cancels, and an empty value clears the display name.
 */
export function DisplayNameEditor({ project }: { project: CollectionInfo }) {
  const fieldId = useId();
  const pencilRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const save = useSetDisplayName(project.name);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function open() {
    setDraft(project.display_name ?? "");
    setProblem(null);
    setSaved(false);
    save.reset();
    setEditing(true);
  }

  function close() {
    returnFocus.current = true;
    setEditing(false);
  }

  // The pencil is gone while editing, so focus returns to it once the form has closed.
  useEffect(() => {
    if (editing || !returnFocus.current) return;
    returnFocus.current = false;
    pencilRef.current?.focus();
  }, [editing]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const found = displayNameProblem(draft);
    setProblem(found);
    if (found !== null) return;
    save.mutate(draft, {
      onSuccess: () => {
        setSaved(true);
        close();
      },
    });
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    close();
  }

  return (
    <div className="flex min-w-0 flex-col gap-1">
      {editing ? (
        <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
          <Label htmlFor={fieldId} className="sr-only">
            Display name
          </Label>
          <Input
            id={fieldId}
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            aria-invalid={problem !== null}
            aria-describedby={problem !== null ? `${fieldId}-problem` : undefined}
            className="w-72 max-w-full"
          />
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={close}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex min-w-0 items-center gap-1">
          <h2 className="text-section-title font-semibold break-words">{collectionTitle(project)}</h2>
          <Button
            ref={pencilRef}
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Edit display name of ${project.name}`}
            onClick={open}
          >
            <Pencil aria-hidden="true" />
          </Button>
        </div>
      )}
      <span className="font-mono text-meta text-muted-foreground break-all">Collection name: {project.name}</span>
      {problem !== null ? (
        <p id={`${fieldId}-problem`} role="alert" className="text-meta text-status-error-label">
          {problem}
        </p>
      ) : null}
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => submit()} /> : null}
      {saved && !editing ? (
        <p role="status" className="text-meta text-status-success-label">
          Display name saved.
        </p>
      ) : null}
    </div>
  );
}
