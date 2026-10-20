import { Pencil } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useUpdateProfile } from "../api/mutations";
import type { ProfileRecord } from "../api/profiles";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

/** The server limit of `PATCH /v1/profiles/{id}` (`routes/profiles.py`). */
export const DESCRIPTION_LIMIT = 1000;

/**
 * The description of a profile in the canvas header. A built-in profile shows
 * the text only. A user profile adds a pencil that edits it in place: Enter or
 * Save sends the trimmed text, Escape or Cancel closes the field with no
 * request. A refused save keeps the old text and offers Retry.
 */
export function ProfileDescriptionEditor({ profile }: { profile: ProfileRecord }) {
  const fieldId = useId();
  const pencilRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const save = useUpdateProfile(profile.profile_id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  // The pencil is gone while editing, so focus returns to it once the form has closed.
  useEffect(() => {
    if (editing || !returnFocus.current) return;
    returnFocus.current = false;
    pencilRef.current?.focus();
  }, [editing]);

  if (profile.kind === "builtin") {
    return profile.description === "" ? null : <p className="text-meta text-muted-foreground">{profile.description}</p>;
  }

  function open() {
    setDraft(profile.description);
    setProblem(null);
    save.reset();
    setEditing(true);
  }

  function close() {
    returnFocus.current = true;
    setEditing(false);
  }

  function send(description: string) {
    save.mutate({ description }, { onSettled: close });
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const description = draft.trim();
    if (description.length > DESCRIPTION_LIMIT) {
      setProblem(`Use at most ${DESCRIPTION_LIMIT} characters.`);
      return;
    }
    setProblem(null);
    send(description);
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
            Profile description
          </Label>
          <Input
            id={fieldId}
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            aria-invalid={problem !== null}
            aria-describedby={problem !== null ? `${fieldId}-problem` : undefined}
            className="w-96 max-w-full"
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
          <p className={profile.description === "" ? "text-meta text-muted-foreground" : "text-meta text-muted-foreground break-words"}>
            {profile.description === "" ? "No description" : profile.description}
          </p>
          <Button ref={pencilRef} type="button" variant="ghost" size="icon-xs" aria-label={`Edit the description of ${profile.title}`} onClick={open}>
            <Pencil aria-hidden="true" />
          </Button>
        </div>
      )}
      {problem !== null ? (
        <p id={`${fieldId}-problem`} role="alert" className="text-meta text-status-error-label">
          {problem}
        </p>
      ) : null}
      {save.isError && !editing ? <ErrorNotice error={save.error} onRetry={() => send(save.variables?.description ?? profile.description)} /> : null}
    </div>
  );
}
