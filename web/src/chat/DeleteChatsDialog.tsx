import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";

export interface DeleteRequest {
  heading: string;
  /** States how many chats the delete removes. */
  detail: string;
  confirmLabel: string;
  run: () => Promise<unknown>;
}

interface DeleteChatsDialogProps {
  request: DeleteRequest | null;
  onClose: () => void;
}

/** Asks before a permanent delete of chats or a folder. The text always says how many chats go. */
export function DeleteChatsDialog({ request, onClose }: DeleteChatsDialogProps) {
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const returnFocus = useReturnFocus();

  function close() {
    setFailure(null);
    onClose();
  }

  async function confirm() {
    if (request === null) return;
    setBusy(true);
    try {
      await request.run();
      close();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={request !== null} onOpenChange={(open) => (open ? undefined : close())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{request?.heading ?? ""}</DialogTitle>
          <DialogDescription>{request?.detail ?? ""}</DialogDescription>
        </DialogHeader>
        {failure !== null ? <ErrorNotice error={failure} onRetry={() => void confirm()} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={close}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" disabled={busy} onClick={() => void confirm()}>
            {request?.confirmLabel ?? "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
