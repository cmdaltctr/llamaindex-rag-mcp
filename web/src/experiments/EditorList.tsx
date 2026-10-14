import type { FetchLike } from "../api/client";
import { stopEditor, type EditorInfo } from "../api/plugins";
import { ConfirmAction } from "./ConfirmAction";

interface EditorListProps {
  editors: EditorInfo[];
  names: Record<string, string>;
  fetchImpl?: FetchLike;
  onChanged: () => void;
}

/** Editors this server started. Each runs in its own browser tab; this page never embeds one. */
export function EditorList({ editors, names, fetchImpl, onChanged }: EditorListProps) {
  if (editors.length === 0) return null;
  return (
    <ul className="plain-list editor-list" aria-label="Running editors">
      {editors.map((editor) => (
        <li key={editor.launch_id} className="editor-list__item">
          <span className="type-code" dir="ltr">
            {editor.notebook}
          </span>
          <span className="type-meta">
            {editor.plugin}, context {editor.experiment_context ? (names[editor.experiment_context] ?? editor.experiment_context) : "none"},{" "}
            <span dir="ltr">{editor.url_without_token}</span>
          </span>
          <ConfirmAction
            label={`Stop editor ${editor.launch_id}`}
            text="Stop"
            warning="Stopping ends this editor process. Notebook files are kept. Unsaved changes in the editor tab are lost."
            confirmLabel="Confirm stop"
            cancelLabel="Keep running"
            onConfirm={async () => {
              await stopEditor(editor.launch_id, { fetchImpl });
              onChanged();
            }}
          />
        </li>
      ))}
    </ul>
  );
}
