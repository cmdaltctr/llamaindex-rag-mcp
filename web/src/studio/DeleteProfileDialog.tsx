import { ApiError } from "../api/client";
import { useDeleteProfile } from "../api/mutations";
import type { ProfileRecord } from "../api/profiles";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "./useReturnFocus";

interface DeleteProfileDialogProps {
  profile: ProfileRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after the server has deleted the profile, so the page can say so. */
  onDeleted?: () => void;
}

/** The sentence that names the collections which block a delete. */
export function inUseLine(names: readonly string[]): string {
  return `You cannot delete this profile while collections use it: ${names.join(", ")}.`;
}

/** The collection names in the body of a 409 refusal, or `null` for any other failure. */
function refusedBy(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const names = (error.body as { used_by?: unknown } | undefined)?.used_by;
  return Array.isArray(names) ? names.filter((name): name is string => typeof name === "string") : null;
}

/** Confirms before deleting a user profile. A 409 names the collections and keeps the profile. */
export function DeleteProfileDialog({ profile, open, onOpenChange, onDeleted }: DeleteProfileDialogProps) {
  const remove = useDeleteProfile(profile.profile_id);
  const returnFocus = useReturnFocus();
  const blockedBy = refusedBy(remove.error);

  async function confirm() {
    try {
      await remove.mutateAsync();
    } catch {
      return;
    }
    onOpenChange(false);
    onDeleted?.();
  }

  function change(next: boolean) {
    if (!next) remove.reset();
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Delete ${profile.title}?`}</DialogTitle>
          <DialogDescription>Collections can no longer pick this profile. Past runs stay in Experiments.</DialogDescription>
        </DialogHeader>
        {blockedBy !== null ? (
          <p role="alert" className="text-ui text-status-error-label">
            {inUseLine(blockedBy)}
          </p>
        ) : null}
        {remove.isError && blockedBy === null ? <ErrorNotice error={remove.error} onRetry={() => void confirm()} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => change(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" disabled={remove.isPending || blockedBy !== null} onClick={() => void confirm()}>
            Delete profile
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
