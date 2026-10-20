import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { documentReadingQuery } from "../api/queries";
import type { DocumentReadingKey, DocumentReadingSetting, DocumentReadingState } from "../api/settingsDocumentReading";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { READING_ROWS, readingChoices } from "./documentReadingWords";
import { ReadingSettingRow } from "./ReadingSettingRow";
import { RestartDialog } from "./RestartDialog";

export const IDENTITY_NOTE = "These settings are part of the index identity. After a restart, the next ingest can read existing files again.";

const PDF_KEYS: readonly DocumentReadingKey[] = ["pdf_reader"];

interface RestartRequest {
  change: string;
  plural: boolean;
}

/** The lines a row shows under its value: the reader the engine resolved, and the worker command that replaces the primary engine. */
function rowNotes(setting: DocumentReadingSetting, state: DocumentReadingState): string[] {
  if (setting.key === "pdf_reader" && state.pdf_reader_in_use !== null && state.pdf_reader_in_use !== setting.value) return [`In use: ${state.pdf_reader_in_use}`];
  if (setting.key === "ocr_engine_primary" && state.ocr.worker_command_set) return ["OCR_WORKER_COMMAND is set, so it replaces the primary engine."];
  return [];
}

/** After a save, the restart prompt for what waits: the saved key alone, or the section when other keys wait too. */
function restartFor(state: DocumentReadingState, key: DocumentReadingKey): RestartRequest | null {
  const waiting = state.settings.filter((setting) => setting.restart_pending);
  if (waiting.length === 0) return null;
  if (waiting.length === 1 && waiting[0]?.key === key) return { change: READING_ROWS[key].label, plural: false };
  return { change: "Document reading settings", plural: true };
}

function ReadingCard({ title, state, keys, onSaved }: { title: string; state: DocumentReadingState; keys: (key: DocumentReadingKey) => boolean; onSaved: (state: DocumentReadingState, key: DocumentReadingKey) => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <div className="flex flex-col gap-5">
        {state.settings
          .filter((setting) => keys(setting.key))
          .map((setting) => (
            <ReadingSettingRow
              key={setting.key}
              setting={setting}
              words={READING_ROWS[setting.key]}
              choices={readingChoices(READING_ROWS[setting.key].kind, state)}
              notes={rowNotes(setting, state)}
              onSaved={(next) => onSaved(next, setting.key)}
            />
          ))}
      </div>
    </Card>
  );
}

/** The PDF reader and the OCR settings, saved to `omrg.jsonc` for the next launch of `omrg web`. */
export function DocumentReadingSection() {
  const query = useQuery(documentReadingQuery(useApi()));
  const [restart, setRestart] = useState<RestartRequest | null>(null);
  const state = query.data;
  const saved = (next: DocumentReadingState, key: DocumentReadingKey) => setRestart(restartFor(next, key));

  return (
    <section aria-labelledby="settings-document-reading" className="flex flex-col gap-4">
      <h2 id="settings-document-reading" className="text-section-title font-semibold">
        Document reading
      </h2>
      <ul className="list-disc ps-5 text-meta text-muted-foreground">
        <li>These settings apply after a restart of omrg web. Saving does not change the reading in force.</li>
        <li>{IDENTITY_NOTE}</li>
        <li>A Read document step in a pipeline can choose its own reader.</li>
      </ul>
      {state === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <ReadingCard title="PDF reading" state={state} keys={(key) => PDF_KEYS.includes(key)} onSaved={saved} />
          <ReadingCard title="OCR" state={state} keys={(key) => !PDF_KEYS.includes(key)} onSaved={saved} />
          {state.ocr.workers_dir === null ? (
            <p className="text-meta text-muted-foreground">OCR_WORKERS_DIR is not set, so no OCR engine can run.</p>
          ) : (
            <p className="text-meta text-muted-foreground">
              {"OCR engines folder: "}
              <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
                {state.ocr.workers_dir}
              </code>
            </p>
          )}
        </>
      )}
      <RestartDialog change={restart?.change ?? null} plural={restart?.plural} note={IDENTITY_NOTE} onLater={() => setRestart(null)} />
    </section>
  );
}
