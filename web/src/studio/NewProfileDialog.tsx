import { useId, useState, type FormEvent } from "react";
import { useCreateProfile } from "../api/mutations";
import type { ProfileRecord } from "../api/profiles";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useRoute } from "../lib/RouteProvider";
import { useReturnFocus } from "./useReturnFocus";

interface NewProfileDialogProps {
  /** The profile to copy, or `null` for an empty profile. */
  source: ProfileRecord | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function NewProfileForm({ source, onOpenChange }: Omit<NewProfileDialogProps, "open">) {
  const fieldId = useId();
  const { navigate } = useRoute();
  const create = useCreateProfile();
  const [title, setTitle] = useState(source === null ? "" : `${source.title} copy`);
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = title.trim();
    if (trimmed === "") {
      setProblem("Enter a title.");
      return;
    }
    setProblem(null);
    create.mutate(
      { source: source?.profile_id ?? null, title: trimmed },
      {
        onSuccess: (created) => {
          onOpenChange(false);
          navigate({ area: "studio", profileId: created.profile_id, purpose: null });
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={fieldId}>Title</Label>
        <Input
          id={fieldId}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-invalid={problem !== null}
          aria-describedby={problem !== null ? `${fieldId}-problem` : undefined}
        />
        {problem !== null ? (
          <p id={`${fieldId}-problem`} role="alert" className="text-meta text-status-error-label">
            {problem}
          </p>
        ) : null}
      </div>
      {create.isError ? <ErrorNotice error={create.error} onRetry={() => submit()} /> : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending}>
          Create profile
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * Asks for the title before anything exists, because the server makes the
 * permanent profile ID from it. A copy proposes "<source title> copy". On
 * success the new profile opens in Studio.
 */
export function NewProfileDialog({ source, open, onOpenChange }: NewProfileDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{source === null ? "New empty profile" : `Duplicate ${source.title}`}</DialogTitle>
          <DialogDescription>The profile ID is made from this title. It cannot change later.</DialogDescription>
        </DialogHeader>
        <NewProfileForm source={source} onOpenChange={onOpenChange} />
      </DialogContent>
    </Dialog>
  );
}
