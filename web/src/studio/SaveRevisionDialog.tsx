import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import type { Purpose } from "../lib/routes";
import { saveWarning } from "./profileCopy";
import { useReturnFocus } from "./useReturnFocus";

interface SaveRevisionDialogProps {
  purpose: Purpose;
  /** The collections that use the profile of the open pipeline. */
  collections: readonly string[];
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Asks before a new revision changes how the collections of a profile in use ingest, search or answer. */
export function SaveRevisionDialog({ purpose, collections, open, onConfirm, onCancel }: SaveRevisionDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>Save this revision?</DialogTitle>
          <DialogDescription>{saveWarning(purpose, collections)}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm}>
            Save revision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
