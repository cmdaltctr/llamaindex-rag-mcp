import { useId, useState, type FormEvent } from "react";
import type { DocumentReadingSetting, DocumentReadingState } from "../api/settingsDocumentReading";
import { useSaveDocumentReading } from "../api/settingsMutations";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { sourceText } from "./connectionWords";
import { draftText, draftValue, fractionError, readingText, type ReadingChoice, type ReadingRowWords } from "./documentReadingWords";
import { ReadingControl } from "./ReadingControl";
import { SaveErrorNotice } from "./SaveErrorNotice";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const META = "text-meta text-muted-foreground";

interface ReadingSettingRowProps {
  setting: DocumentReadingSetting;
  words: ReadingRowWords;
  choices: ReadingChoice[];
  /** Extra lines for this row, such as the reader in use or the worker command notice. */
  notes: string[];
  /** Called with the state the server returned after a good save. */
  onSaved: (state: DocumentReadingState) => void;
}

/**
 * One document reading key: the value in force, its source, the default, and
 * the value saved for the next launch with "Restart to apply" when it differs.
 * Edit opens the control filled with the value the next launch will use. A key
 * from the environment or `.env` has no Edit and names the variable to remove.
 */
export function ReadingSettingRow({ setting, words, choices, notes, onSaved }: ReadingSettingRowProps) {
  const id = useId();
  const save = useSaveDocumentReading();
  const [draft, setDraft] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const { label, kind } = words;
  const next = setting.saved ?? setting.value;
  const start = draftText(next);
  const nextReason = choices.find((choice) => choice.value === next)?.reason ?? null;

  function close() {
    setDraft(null);
    setRefusal(null);
    save.reset();
  }

  function change(text: string) {
    setDraft(text);
    setRefusal(null);
  }

  function send(value: DocumentReadingSetting["value"] | null) {
    save.mutate(
      { [setting.key]: value },
      {
        onSuccess: (state) => {
          close();
          onSaved(state);
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (draft === null || draft === start) return;
    const message = kind === "fraction" ? fractionError(draft) : null;
    if (message !== null) return setRefusal(message);
    send(draftValue(kind, draft));
  }

  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1.5">
      <p className={META}>{label}</p>
      {draft === null ? (
        <code dir="ltr" className={CODE}>
          {readingText(setting.value)}
        </code>
      ) : null}
      <p className={META}>{words.help}</p>
      <p className={META}>
        {sourceText(setting.source)}
        {" · Default: "}
        <span dir="ltr">{readingText(setting.default)}</span>
      </p>
      {setting.restart_pending ? (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-ui">
            {"Saved for the next launch: "}
            <code dir="ltr" className={CODE}>
              {readingText(setting.saved)}
            </code>
          </p>
          <Badge variant="warning">Restart to apply</Badge>
        </div>
      ) : null}
      {draft === null && kind === "engine" && nextReason !== null ? <p className={META}>{`${String(next)}: ${nextReason}`}</p> : null}
      {notes.map((note) => (
        <p key={note} className="text-ui">
          {note}
        </p>
      ))}
      {setting.locked ? <p className={META}>{setting.lock_reason ?? "Read-only here."}</p> : null}
      {draft === null && !setting.locked ? (
        <div>
          <Button type="button" variant="outline" size="sm" aria-label={`Edit ${label}`} onClick={() => setDraft(start)}>
            Edit
          </Button>
        </div>
      ) : null}
      {draft !== null ? (
        <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
          <ReadingControl id={id} label={label} kind={kind} draft={draft} choices={choices} refusal={refusal} onChange={change} />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={draft === start || save.isPending}>
              Save
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Cancel
            </Button>
            {setting.saved !== null ? (
              <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => send(null)}>
                Use default
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </div>
  );
}
