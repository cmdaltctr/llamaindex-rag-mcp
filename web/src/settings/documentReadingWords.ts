import type { DocumentReadingKey, DocumentReadingState, DocumentReadingValue } from "../api/settingsDocumentReading";

/** How a row edits its value: a select of readers, units or engines, a switch, or a number from 0 to 1. */
export type ReadingKind = "reader" | "unit" | "engine" | "switch" | "fraction";

export interface ReadingRowWords {
  label: string;
  kind: ReadingKind;
  /** One plain line on what the setting does. */
  help: string;
}

export const READING_ROWS: Record<DocumentReadingKey, ReadingRowWords> = {
  pdf_reader: { label: "PDF reader", kind: "reader", help: "Reads the text of each PDF. auto tries LiteParse, then pypdfium2, then pypdf." },
  ocr_fallback_enabled: { label: "OCR fallback", kind: "switch", help: "Off means no PDF goes to an OCR engine." },
  ocr_fallback_min_confidence: { label: "Lowest text confidence", kind: "fraction", help: "A text PDF below this confidence goes to OCR. 0 sends none." },
  ocr_fallback_page_fraction: { label: "OCR page fraction", kind: "fraction", help: "The share of flagged pages that sends a PDF to OCR. 0 sends none." },
  ocr_routing_unit: { label: "OCR routing unit", kind: "unit", help: "document sends the whole PDF to OCR. page sends only the flagged pages." },
  ocr_engine_primary: { label: "Primary engine", kind: "engine", help: "The OCR engine for every request." },
  ocr_engine_fallback: { label: "Fallback engine", kind: "engine", help: "The OCR engine to use when the primary engine cannot run." },
  ocr_maths_routing_enabled: { label: "Maths routing", kind: "switch", help: "Finds maths fonts and sends those pages to OCR." },
  ocr_maths_page_fraction: { label: "Maths page fraction", kind: "fraction", help: "The share of maths pages that sends a whole PDF to OCR. 0 turns this off." },
};

export const ROUTING_UNITS = ["document", "page"] as const;

export const FRACTION_ERROR = "Enter a number from 0 to 1.";

/** One option of a select row. A disabled option cannot be chosen; `reason` says why it cannot run. */
export interface ReadingChoice {
  value: string;
  label: string;
  disabled: boolean;
  reason: string | null;
}

/** The options of a select row, from what the server reports. A switch or a number row has none. */
export function readingChoices(kind: ReadingKind, state: DocumentReadingState): ReadingChoice[] {
  if (kind === "reader") {
    return state.pdf_readers.map(({ name, available, reason }) => ({ value: name, label: available ? name : `${name} (not installed)`, disabled: !available, reason }));
  }
  if (kind === "engine") {
    return state.ocr.engines.map(({ name, available, reason }) => ({
      value: name,
      label: available ? name : `${name} (${reason?.startsWith("Not provisioned") ? "not provisioned" : "not available"})`,
      disabled: false,
      reason: available ? null : reason,
    }));
  }
  if (kind === "unit") return ROUTING_UNITS.map((unit) => ({ value: unit, label: unit, disabled: false, reason: null }));
  return [];
}

/** A value as the row shows it. A saved empty engine name means no fallback (design D8). */
export function readingText(value: DocumentReadingValue | null): string {
  if (value === null) return "Not set";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (value === "") return "None (no fallback)";
  return String(value);
}

/** The editor text of a value: `true` or `false` for a switch, the number or name as text otherwise. */
export function draftText(value: DocumentReadingValue | null): string {
  return value === null ? "" : String(value);
}

/** The editor text as the JSON value the route takes. */
export function draftValue(kind: ReadingKind, text: string): DocumentReadingValue {
  if (kind === "switch") return text === "true";
  if (kind === "fraction") return Number(text);
  return text;
}

/** The refusal for a typed fraction, or `null` when it is a number from 0 to 1. */
export function fractionError(text: string): string | null {
  const number = Number(text);
  return text.trim() === "" || !Number.isFinite(number) || number < 0 || number > 1 ? FRACTION_ERROR : null;
}
