/**
 * Evidence helpers: score-kind labels, bounded previews and the search for
 * ranked rows, citations and answers inside run outputs.
 *
 * Bounds match the server preview limits (`core/workspace/artefacts.py`):
 * 100 rows and 4 KiB of UTF-8 text per preview.
 */
export const MAX_PREVIEW_ROWS = 100;
export const MAX_TEXT_BYTES = 4 * 1024;

const SCORE_KINDS: Record<string, { label: string; digits: number | null }> = {
  reranker_sigmoid_v1: { label: "Reranker score", digits: 4 },
  rrf_v1: { label: "RRF score", digits: 4 },
  dense_similarity_v1: { label: "Dense similarity", digits: 4 },
  native_fts_v1: { label: "Full-text score", digits: 4 },
  sparse_rank_v1: { label: "Rank only", digits: null },
};

/** Label and formatted value. A rank-only kind never shows a number. */
export function scoreText(score: unknown, kind: unknown): { label: string; value: string | null } {
  const known = typeof kind === "string" ? SCORE_KINDS[kind] : undefined;
  const label = known?.label ?? (typeof kind === "string" && kind ? `Score (${kind})` : "Score, kind not reported");
  if (known?.digits === null) return { label, value: null };
  const value = typeof score === "number" && Number.isFinite(score) ? score.toPrecision(known?.digits ?? 4) : null;
  return { label, value };
}

/** The first `limit` bytes of UTF-8 text, without a broken last character. */
export function boundText(text: string, limit = MAX_TEXT_BYTES): { text: string; truncated: boolean } {
  const bytes = new TextEncoder().encode(text);
  if (bytes.length <= limit) return { text, truncated: false };
  const cut = new TextDecoder().decode(bytes.slice(0, limit)).replace(/�+$/, "");
  return { text: cut, truncated: true };
}

export type Row = Record<string, unknown>;

/** `all` keeps every row, for "Open full output" when the preview shows only the first ones. */
export type EvidenceItem =
  | { name: string; kind: "rows"; rows: Row[]; total: number; all: Row[] }
  | { name: string; kind: "citations"; citations: Row[]; total: number; all: Row[] }
  | { name: string; kind: "answer"; text: string };

function isRow(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function looksRanked(rows: Row[]): boolean {
  return rows.length > 0 && rows.every((row) => "chunk_id" in row || "score_kind" in row || "text" in row);
}

function collect(name: string, value: unknown, depth: number, found: EvidenceItem[]) {
  if (Array.isArray(value)) {
    const rows = value.filter(isRow);
    if (rows.length === value.length && looksRanked(rows)) {
      const kind = name.endsWith("citations") ? "citations" : "rows";
      const bounded = rows.slice(0, MAX_PREVIEW_ROWS);
      const total = rows.length;
      found.push(kind === "rows" ? { name, kind, rows: bounded, total, all: rows } : { name, kind, citations: bounded, total, all: rows });
    }
    return;
  }
  if (!isRow(value) || depth > 2) return;
  if (typeof value.answer === "string") found.push({ name, kind: "answer", text: value.answer });
  for (const key of ["rows", "results", "citations", "evidence"]) {
    if (key in value) collect(`${name}.${key}`, value[key], depth + 1, found);
  }
}

/** Ranked rows, citations and answers in graph outputs, in output order. */
export function findEvidence(outputs: Record<string, unknown>): EvidenceItem[] {
  const found: EvidenceItem[] = [];
  for (const [name, value] of Object.entries(outputs)) collect(name, value, 0, found);
  return found;
}

/** Earlier-stage ranks that a row still carries, for showing rank changes. */
export function stageRanks(row: Row): string[] {
  const names: Record<string, string> = { dense_rank: "dense", sparse_rank: "sparse", fused_rank: "fused" };
  return Object.entries(names).flatMap(([key, label]) => (typeof row[key] === "number" ? [`${label} rank ${row[key]}`] : []));
}
