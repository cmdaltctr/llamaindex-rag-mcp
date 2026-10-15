import { useEffect } from "react";
import type { DeleteResult, DeleteSelector, DocumentInfo } from "../api/documents";
import { useDeleteDocuments } from "../api/mutations";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { plural } from "../lib/labels";
import { ConfirmationNote, FlowButtons } from "./FlowControls";
import { usePreviewConfirm } from "./usePreviewConfirm";

/** A whole collection, or one source of it. */
export type DeleteTarget = { kind: "collection" } | { kind: "source"; source: DocumentInfo };

interface DeleteDialogProps {
  collection: string;
  target: DeleteTarget;
  onClose: () => void;
  /** Called once a whole collection is gone, so the view can leave it. */
  onCollectionDeleted: () => void;
}

/** A source with a stable id is selected by that id; a legacy row by its stored path. */
function selectorFor(target: DeleteTarget): DeleteSelector {
  if (target.kind === "collection") return {};
  const { source_id: id, source } = target.source;
  return id !== null ? { metadata_filter: { source_id: id } } : { path: source };
}

function describe(collection: string, target: DeleteTarget, preview: DeleteResult): string {
  const count = preview.would_delete ?? 0;
  if (target.kind === "collection") return `Deleting removes the whole collection ${collection} (${plural(count, "chunk")}).`;
  const id = target.source.source_id ?? "no stable ID";
  return `Deleting removes ${plural(count, "chunk")} of ${target.source.source} (${id}) from ${collection}. The original file is not touched.`;
}

/** Preview, then confirm with the preview token (design D8). */
export function DeleteDialog({ collection, target, onClose, onCollectionDeleted }: DeleteDialogProps) {
  const remove = useDeleteDocuments(collection);
  const selector = selectorFor(target);
  const flow = usePreviewConfirm(
    () => remove.mutateAsync({ selector, step: { preview: true } }),
    async (token) => {
      const result = await remove.mutateAsync({ selector, step: { token } });
      if (result.mode === "collection") onCollectionDeleted();
      return result;
    },
    "previewing",
  );
  const { loadPreview } = flow;
  const { phase, preview, result } = flow.state;

  useEffect(() => {
    void loadPreview();
    // Preview once when the dialog opens; "Preview again" handles later previews.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const count = preview?.would_delete ?? 0;
  const title = target.kind === "collection" ? "Delete collection" : "Delete source";
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>Review what will be removed. Nothing changes until you confirm.</DialogDescription>
        </DialogHeader>
        {preview && (phase === "ready" || phase === "confirming") ? <p>{describe(collection, target, preview)}</p> : null}
        {preview && count === 0 && phase === "ready" ? (
          <p className="text-meta text-muted-foreground">Nothing matches, so there is nothing to delete.</p>
        ) : null}
        {phase === "ready" ? <ConfirmationNote confirmation={preview?.confirmation} /> : null}
        {phase === "done" && result ? (
          <p role="status" className="text-status-success-label">
            {result.mode === "collection" ? `Collection ${collection} deleted.` : `Removed ${plural(result.chunks_removed ?? 0, "chunk")}.`}
          </p>
        ) : null}
        <FlowButtons
          state={flow.state}
          confirmLabel="Confirm deletion"
          canConfirm={count > 0 || target.kind === "collection"}
          onConfirm={() => void flow.runConfirm()}
          onPreviewAgain={() => void flow.runPreview()}
          onCancel={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}
