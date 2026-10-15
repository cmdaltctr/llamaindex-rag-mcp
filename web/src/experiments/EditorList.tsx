import type { EditorInfo } from "../api/plugins";
import { ConfirmAction } from "./ConfirmAction";
import { useStopEditor } from "./mutations";

interface EditorListProps {
  editors: EditorInfo[];
  names: Record<string, string>;
}

/** Editors this server started. Each runs in its own browser tab; this page never embeds one. */
export function EditorList({ editors, names }: EditorListProps) {
  const stop = useStopEditor();
  if (editors.length === 0) return null;
  return (
    <ul aria-label="Running editors" className="flex flex-col gap-2">
      {editors.map((editor) => (
        <li key={editor.launch_id} className="flex flex-col gap-1 rounded-small border border-border p-3">
          <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
            {editor.notebook}
          </code>
          <span className="text-meta text-muted-foreground">
            {editor.plugin}, context {editor.experiment_context ? (names[editor.experiment_context] ?? editor.experiment_context) : "none"},{" "}
            <span dir="ltr">{editor.url_without_token}</span>
          </span>
          <div>
            <ConfirmAction
              label={`Stop editor ${editor.launch_id}`}
              text="Stop"
              warning="Stopping ends this editor process. Notebook files are kept. Unsaved changes in the editor tab are lost."
              confirmLabel="Confirm stop"
              cancelLabel="Keep running"
              onConfirm={() => stop.mutateAsync(editor.launch_id)}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
