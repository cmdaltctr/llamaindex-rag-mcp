import { Pencil } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ProfileRecord } from "../api/profiles";
import { useUpdateProfile } from "../api/mutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const HEADING_CLASS = {
  1: "text-page-title font-semibold outline-none",
  2: "text-section-title font-semibold",
  3: "text-subsection-title font-semibold leading-snug",
} as const;

interface ProfileTitleEditorProps {
  profile: ProfileRecord;
  /** The heading level of the title. The gallery card uses 3 and the canvas header 1. */
  level?: 1 | 2 | 3;
}

/**
 * The title of a profile. A built-in profile shows the title only. A user
 * profile adds a pencil that edits the title in place, and the permanent ID in
 * grey underneath. Enter saves, Escape cancels. A refused save closes the field,
 * keeps the old title and offers Retry with the title that was typed.
 */
export function ProfileTitleEditor({ profile, level = 2 }: ProfileTitleEditorProps) {
  // The page heading takes focus after navigation (the shell moves it there), so it needs tabIndex -1.
  const Heading = `h${level}` as "h1" | "h2" | "h3";
  const fieldId = useId();
  const pencilRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const save = useUpdateProfile(profile.profile_id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function open() {
    setDraft(profile.title);
    setProblem(null);
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

  function send(title: string) {
    save.mutate({ title }, { onSettled: close });
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const title = draft.trim();
    if (title === "") {
      setProblem("Enter a title.");
      return;
    }
    setProblem(null);
    send(title);
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    close();
  }

  if (profile.kind === "builtin") return <Heading tabIndex={level === 1 ? -1 : undefined} className={`${HEADING_CLASS[level]} break-words`}>{profile.title}</Heading>;

  return (
    <div className="flex min-w-0 flex-col gap-1">
      {editing ? (
        <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
          <Label htmlFor={fieldId} className="sr-only">
            Profile title
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
          <Heading tabIndex={level === 1 ? -1 : undefined} className={`${HEADING_CLASS[level]} break-words`}>{profile.title}</Heading>
          <Button ref={pencilRef} type="button" variant="ghost" size="icon-sm" aria-label={`Rename ${profile.title}`} onClick={open}>
            <Pencil aria-hidden="true" />
          </Button>
        </div>
      )}
      <span className="font-mono text-meta text-muted-foreground break-all">Profile ID: {profile.profile_id}</span>
      {problem !== null ? (
        <p id={`${fieldId}-problem`} role="alert" className="text-meta text-status-error-label">
          {problem}
        </p>
      ) : null}
      {save.isError && !editing ? <ErrorNotice error={save.error} onRetry={() => send(save.variables?.title ?? profile.title)} /> : null}
    </div>
  );
}
