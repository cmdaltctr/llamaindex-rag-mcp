import { useEffect } from "react";
import type { FetchLike } from "../../api/client";
import { deleteDocuments, type DeleteResult, type DeleteSelector, type DocumentInfo } from "../../api/documents";
import { plural } from "../shared/labels";
import { ConfirmationNote, FlowButtons } from "./FlowControls";
import { usePreviewConfirm } from "./usePreviewConfirm";

/** A whole collection, or one source of it. */
export type DeleteTarget = { kind: "collection" } | { kind: "source"; source: DocumentInfo };

interface DeletePanelProps {
  collection: string;
  target: DeleteTarget;
  fetchImpl?: FetchLike;
  onClose: () => void;
  onDeleted: () => void;
}

/** A source with a stable id is selected by that id; a legacy row by its stored path. */
function selectorFor(target: DeleteTarget): DeleteSelector {
  if (target.kind === "collection") return {};
  const { source_id: id, source } = target.source;
  return id !== null ? { metadata_filter: { source_id: id } } : { path: source };
}

function describe(collection: string, target: DeleteTarget, preview: DeleteResult): string {
  const count = preview.would_delete ?? 0;
  if (target.kind === "collection") {
    return `Deleting removes the whole collection ${collection} (${plural(count, "chunk")}).`;
  }
  const id = target.source.source_id ?? "no stable ID";
  return `Deleting removes ${plural(count, "chunk")} of ${target.source.source} (${id}) from ${collection}. The original file is not touched.`;
}

function outcome(collection: string, result: DeleteResult): string {
  if (result.mode === "collection") return `Collection ${collection} deleted.`;
  return `Removed ${plural(result.chunks_removed ?? 0, "chunk")}.`;
}

/** Preview, then confirm with the preview token (design D8). */
export function DeletePanel({ collection, target, fetchImpl, onClose, onDeleted }: DeletePanelProps) {
  const selector = selectorFor(target);
  const flow = usePreviewConfirm(
    () => deleteDocuments(collection, selector, { preview: true }, { fetchImpl }),
    async (token) => {
      const result = await deleteDocuments(collection, selector, { token }, { fetchImpl });
      onDeleted();
      return result;
    },
    "previewing",
  );
  const { loadPreview } = flow;
  const { phase, preview, result } = flow.state;

  useEffect(() => {
    void loadPreview();
    // Preview once when the panel opens; "Preview again" handles later previews.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const count = preview?.would_delete ?? 0;
  return (
    <section className="panel panel--danger" aria-label="Deletion preview">
      <h2 className="type-section-title">Delete {target.kind === "collection" ? "collection" : "source"}</h2>
      {preview && (phase === "ready" || phase === "confirming") ? <p>{describe(collection, target, preview)}</p> : null}
      {preview && count === 0 && phase === "ready" ? <p className="type-meta">Nothing matches, so there is nothing to delete.</p> : null}
      {phase === "ready" ? <ConfirmationNote confirmation={preview?.confirmation} /> : null}
      {phase === "done" && result ? <p className="notice notice--success">{outcome(collection, result)}</p> : null}
      <FlowButtons
        state={flow.state}
        confirmLabel="Confirm deletion"
        canConfirm={count > 0 || target.kind === "collection"}
        onConfirm={() => void flow.runConfirm()}
        onPreviewAgain={() => void flow.runPreview()}
        onCancel={onClose}
      />
    </section>
  );
}
