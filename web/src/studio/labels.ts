/**
 * Plain labels for operation parameters. The lookup order is the lever path
 * (so one setting reads the same on every step), then the parameter name,
 * then the schema title in sentence case. The labels live in the web because
 * the backend writes Pydantic titles such as "Top K".
 */
import type { JsonValue } from "../api/pipelines";

interface Labelled {
  name: string;
  title: string;
  lever?: string;
}

const FIELD_LABELS: Record<string, string> = {
  "retrieval.top_k": "Number of results",
  "retrieval.similarity_threshold": "Minimum similarity",
  "retrieval.rerank_enabled": "Reranker",
  "retrieval.hybrid_rrf_k": "Fusion constant (k)",
  "retrieval.rerank_fetch_multiplier": "Rerank candidate factor",
  "chunking.chunk_size": "Chunk size",
  "chunking.chunk_overlap": "Chunk overlap",
  "chunking.markdown_chunk_size": "Markdown chunk size",
  "chunking.strategy_fallback": "Fallback chunking",
  "chunking.code_chunk_lines": "Lines per code chunk",
  "metadata.taxonomy_mode": "Metadata categories",
  "answer.verify_claims": "Check claims",
  collection: "Collection",
  fetch_k: "Candidates to fetch",
  metadata_filter: "Metadata filter",
  pdf_reader: "PDF reader",
  expand_window: "Neighbour chunks to add",
  include_diagnostics: "Include diagnostics",
};

const OPTION_LABELS: Record<string, Record<string, string>> = {
  "chunking.strategy_fallback": { markdown: "Markdown", code: "Code", sentence: "Sentences" },
  "metadata.taxonomy_mode": { category: "Category", file_type: "File type" },
};

/** The label from the map, or `undefined` when the field has none. */
export function mappedFieldLabel(field: Labelled): string | undefined {
  return (field.lever !== undefined ? FIELD_LABELS[field.lever] : undefined) ?? FIELD_LABELS[field.name];
}

function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

export function fieldLabel(field: Labelled): string {
  return mappedFieldLabel(field) ?? sentenceCase(field.title);
}

/** A readable label for one enum option. An option without a label shows its raw value. */
export function optionLabel(field: Labelled, value: JsonValue): string {
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  const labels = field.lever !== undefined ? OPTION_LABELS[field.lever] : undefined;
  return labels?.[raw] ?? raw;
}
