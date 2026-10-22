/**
 * The words of the profile pages in one place, so a test reads the same
 * strings that the page shows. Wording follows the `workspace-studio` spec.
 */
import type { Purpose } from "../lib/routes";

/** The Studio summary: the page header and the navigation hint read it. */
export const STUDIO_SUMMARY =
  "Profiles are groups of steps that you connect into pipelines to ingest files, search them and answer questions. Each collection uses one profile, and the profile decides how that collection works.";

export const PROFILE_HELP_TITLE = "How profiles work";

/** The four lines inside the "How profiles work" disclosure, in order. */
export const PROFILE_HELP_LINES: readonly string[] = [
  "Built-in profiles come with OMRS and are read-only. Your profiles are copies that you can rename, change and delete.",
  "Each profile has three pipelines: Ingest reads files and splits them into chunks, Search finds the best chunks for a question, and Answer writes a cited answer.",
  "To use a profile, pick it for a collection in Knowledge Base, under Profile.",
  "When a collection holds vectors, the embedding model of its profile is locked, because the stored vectors were made with that model.",
];

/** The tab names and the one line under them. */
export const PURPOSE_LABELS: Record<Purpose, string> = { ingest: "Ingest", search: "Search", answer: "Answer" };

export const PURPOSE_LINES: Record<Purpose, string> = {
  ingest: "Reads files, splits them into chunks and stores them in the collection.",
  search: "Finds the chunks that best match a question.",
  answer: "Writes an answer from the best chunks and cites them.",
};

export const READ_ONLY_NOTICE = "Built-in profiles are read-only. Duplicate this profile to change it.";

export const READ_ONLY_RUN_LINE = "Duplicate this profile to save and run its pipelines.";

const collections = (names: readonly string[]): string => `${names.length} ${names.length === 1 ? "collection" : "collections"}`;

/** The text of the "Save this revision?" dialog. It depends on the purpose. */
export function saveWarning(purpose: Purpose, names: readonly string[]): string {
  const list = names.join(", ");
  const one = names.length === 1;
  switch (purpose) {
    case "search":
      return `Saving changes how ${collections(names)} ${one ? "is" : "are"} searched: ${list}.`;
    case "answer":
      return `Saving changes how ${collections(names)} ${one ? "answers" : "answer"} questions: ${list}.`;
    case "ingest":
      return `Saving changes how ${collections(names)} ${one ? "ingests" : "ingest"} files: ${list}. Documents already in these collections keep their old chunks until you ingest them again.`;
  }
}

/** The status line after a save. `names` comes from `affected_collections`. */
export function savedStatus(revisionNumber: number, names: readonly string[]): string {
  return `Saved revision ${revisionNumber}. It now applies to ${collections(names)}: ${names.join(", ")}.`;
}

/** How to edit the canvas. It names the sections "Step settings" and "Connect ports", so change it with them. */
export const CANVAS_INTRO =
  "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports.";
