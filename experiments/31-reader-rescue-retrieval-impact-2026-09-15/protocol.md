# Experiment 31: Reader Rescue Retrieval Impact

- **ID**: `31-reader-rescue-retrieval-impact-2026-09-15`
- **Date**: 2026-09-15
- **Status**: PASS (question answered decisively; negative finding for the candidate — see `report.md`)
- **Operator**: a-build agent (session 2026-09-15), human-approved OpenSpec change `experiment-31-reader-rescue-retrieval-impact`
- **OpenSpec**: `openspec/changes/experiment-31-reader-rescue-retrieval-impact/`

## Purpose

Experiment 30 (2026-09-13) validated that the tiered reader fallback chain
recovers text when `pdf-inspector` returns an empty extraction from a
`text_based` PDF. It did not measure whether the recovered text survives
chunking and embedding well enough to retrieve the gold evidence, nor
whether the LiteParse-first chain retrieves as well as the historical
pypdf-only guard.

**Decision dependent on the result**: whether the current production
fallback chain (`pdf-inspector` → LiteParse OCR-disabled → pypdf, ADR-066)
gives direct downstream retrieval evidence for rescued text, and whether it
retrieves gold evidence at least as well as the pypdf-only rescue
(commit 928f030). A material regression would justify a separate OpenSpec
change to the fallback order; this experiment changes nothing in production.

## Background

- Production `PdfInspectorReader` (ADR-066) retries silent-empty
  `text_based` extractions through liteparse first (extraction-only,
  OCR disabled), then pypdf.
- The historical guard (commit 928f030) retried through pypdf only.
- Experiment 30 measured recovery rates and latency; the LiteParse tier
  recovered 100% of the pathological corpus and was never slower than the
  pypdf retry. LiteParse returned 2-16% fewer characters than pypdf because
  it omits textless pages and joins text differently.
- Open question: does that character difference change retrieval quality?
- No production setting selects a single tier, so cells that differ from
  production use script-local reader mirrors mounted at runtime under the
  production registry name `pdf_inspector` (the sanctioned dispatch
  mechanism, architecture invariant #11; the `Settings` validator
  whitelists `PDF_READER` literals, so experiment names cannot travel
  through the environment). Production code is unchanged.
- In the ingestion pipeline an empty extraction surfaces as a per-file
  failure with zero chunks. For Cell A that failure IS the sanity
  observable: every held-out PDF must fail chunking there with zero
  chunks.

## Cells

Machine-readable definitions live in `cells.json` (task 1.1). Summary:

| Cell | Name | Reader path | Role |
| --- | --- | --- | --- |
| A | `inspector_only` | `pdf-inspector` extraction only, no rescue (script-local mirror) | Sanity check; zero chunks expected for every measured PDF; retrieval score is zero by construction, not a measured comparison |
| B | `tiered_chain` | `pdf-inspector` → LiteParse (OCR disabled) → pypdf — the **current production reader as-is** | Candidate |
| C | `pypdf_guard` | `pdf-inspector` → pypdf — script-local mirror of the historical guard (commit 928f030) | Reference |

Cell B against Cell C is the measured comparison. All cells share the same
chunking, embedding, vector store, retrieval, and reranking path.

Cell A exists to verify the harness and the trigger: every measured PDF must
produce zero chunks there. A Cell-A chunk for a measured PDF means the PDF
fails the trigger check and must not count as held-out evidence (spec
scenario: sanity-check cell produces chunks).

## Controlled Variables (frozen before measured execution)

Frozen in `cells.json` (task 1.2); verified identical across cells at
preflight (task 4.1) and recorded per cell in `output/runtime_manifest_<cell>.json`:

| Variable | Value |
| --- | --- |
| Operational profile | `documents` (top_k=10, rerank_enabled=true, hybrid_enabled=false, strategy_fallback=markdown) |
| Chunker | markdown path, `markdown_chunk_size=1024`, `chunk_size=512`, `chunk_overlap=100` (packaged defaults) |
| Chunk tokenizer | `Qwen/Qwen3-Embedding-4B` rev `5cf2132abc99cad020ac570b19d031efec650f2b` (HF local cache, ADR-063) |
| Embedding provider | `local` → `ollama`, model `qwen3-embedding:0.6b`, base URL `http://localhost:11434` |
| Vector store | `lancedb`, experiment-local URI (`output/lancedb/`), one table per cell |
| Retrieval | top_k=10, dense-only (hybrid off), similarity_threshold=0.0 |
| Reranker | ON via `documents` profile; `cross-encoder/ms-marco-MiniLM-L-6-v2`, ONNX backend |
| Metadata extraction | `disabled` (no LLM calls during ingestion) |
| OCR | `OCR_FALLBACK_ENABLED=false`, `OCR_WORKER_COMMAND` empty; LiteParse tier constructed `ocr_enabled=False`; per-document `ocr_required` recorded from the routing gate, `ocr_used` always observed |
| Query order | frozen order of `queries/qrels.json`; identical in every cell |
| Metadata taxonomy | `category` |

The single manipulated factor is the PDF reader path above the shared
pipeline.

## Corpus

Three groups, frozen in `corpus/manifest.json` and `output/.collection.private.json`:

1. **Development/regression group** (task 2.1): the Experiment 30
   pathological and control documents (`p01_ia_prince`, `p02_ia_managing`,
   `p03_winansi_sloman`, `c01_scanned_kerr`, `c02_healthy_graphrag`), used
   ONLY to verify the harness exercises the expected empty-extraction path.
   They are never indexed into a measured index and never scored. Documents
   inspected while designing the reader rescue do not count as held-out
   evidence (spec: held-out evidence is independent of candidate design).

2. **Held-out group** (tasks 2.2, 2.3): 8 independently sourced natural
   PDFs that meet the exact production rescue trigger — `pdf-inspector`
   classifies `text_based`, `page_count > 0`, and `markdown == ""`.
   Sourcing details, licences, and SHA-256 digests: `corpus/SOURCING.md`.
   Failure types covered: Type A (IA GlyphLessFont text layer, 6 documents)
   and Type B (WinAnsi TrueType without `/ToUnicode`, 2 ACL Anthology
   papers). Excluded partial extractions during sourcing: 1 (recorded;
   `interpretationof00nordiala.pdf`). Target (>= 5 PDFs) met.

3. **Distractor group** (task 2.4): 11 healthy born-digital text-based PDFs
   where the rescue does not fire. Target (10-20) met. Every cell extracts
   distractors identically; they give held-out queries competing documents.

## Gold Evidence and Queries (task 2.5)

- Target: 20-30 queries. Planned: 24 (3 per held-out PDF).
- Gold evidence is a text span labelled from the source PDF via poppler
  `pdftotext` (an extractor used by NO experiment cell) and verified
  against the rendered source. No cell output — pdf-inspector, LiteParse,
  or pypdf — contributes to ground truth (spec: gold evidence is defined
  from the source document).
- Each query is a natural-language question whose answer the span supports.
- Qrels store spans, never chunk identifiers (chunk ids differ per cell).
- Queries and qrels: `queries/qrels.json`, frozen by hash before measured
  runs (task 2.6).

## Text-Span Matching Rule (task 1.4, frozen)

Implemented once in `matching.py`; used unchanged for evidence
recoverability AND retrieval hits in every cell.

1. **Normalise** both span and target text:
   a. Unicode NFKC (folds ligatures such as `ﬁ`);
   b. case-fold (lowercase);
   c. fold typographic quotes/apostrophes/dashes to ASCII equivalents;
   d. rejoin end-of-line hyphen splits (`word-` + whitespace + `word` →
      `wordword`) and fold remaining intra-word hyphens — applied
      identically to span and target;
   e. collapse all whitespace runs to single spaces.
2. **Exact stage**: the normalised span is a substring of the normalised
   target → hit.
3. **Fuzzy stage** (spans of 8+ word tokens only): a hit when >= 0.85 of
   the span's word 8-grams (case-normalised token n-grams, n=8) are
   present in the target's 8-gram set. Spans under 8 tokens use the exact
   stage only.
4. Threshold 0.85 and n=8 are frozen before measured execution.

## Metrics (task 1.3, defined before measured execution)

Primary, reported per cell and paired B-vs-C per query:

- **Evidence recoverability**: fraction of queries whose gold span matches
  the cell's full extraction under the frozen matching rule (parser stage;
  measured before embedding).
- **Evidence Recall@k** (k = 1, 3, 5, 10): fraction of queries with a hit
  in the top-k retrieved chunks (a retrieved chunk hits when it matches the
  gold span under the same rule).
- **MRR@10**: mean reciprocal rank of the first hitting chunk.
- **No-hit rate**: fraction of queries with no hit in the top 10.

Secondary, per cell where available:

- extraction latency (classification seconds + rescue-tier seconds; the
  rescue tier is the median of 3 timed retries, matching Experiment 30's
  noise control);
- chunk count per document and per cell;
- embedding request tokens (from ingestion metrics when exposed);
- index size in bytes (LanceDB table directory).

Retrieval misses on recovered evidence are reported separately from parser
failures (spec: retrieval impact is measured after evidence recovery).

## Validity Controls

- Freeze corpus, distractors, queries, qrels, matching rule, and query
  order before measured runs (`freeze.py` → `output/frozen.manifest.json`).
- One index per cell; each index contains ONLY the held-out and distractor
  groups (development documents are never indexed).
- Identical controlled variables across cells; preflight aborts on any
  unexpected difference (task 4.1).
- Abort a cell when any measured document reports `ocr_used=True`
  (task 4.4). With the OCR worker disabled this must never fire.
- Public outputs carry `doc_id` and SHA-256 only — no private paths, no
  document text (task 4.5). Extracted texts stay in gitignored
  `output/.extractions/`; private paths in gitignored
  `output/.collection.private.json`.
- Record source commit, lockfile hash, effective settings, and index
  identity per cell (runtime manifests, task 3.6).

## Decision Rule

This experiment produces evidence about the existing fallback chain. It
does not change production behaviour. If rescued evidence is recoverable
but retrieval misses it, retain the negative result and investigate
retrieval separately. If Cell B retrieves materially worse than Cell C,
open a separate OpenSpec change before altering the fallback order. The
paired bootstrap confidence interval is reported only if at least 20
measured queries exist; small samples stay small-sample claims.

## Execution Plan

| Step | Script | Output |
| --- | --- | --- |
| Corpus prep | `prepare_corpus.py` | `output/.collection.private.json`, `corpus/manifest.json` |
| Extraction measurement | `measure_extraction.py` | `output/extraction_manifest.json`, `output/.extractions/<cell>/<doc>.txt` |
| Index build | `build_indexes.py` | `output/lancedb/` tables, `output/runtime_manifest_<cell>.json` |
| Preflight | `preflight.py` | `output/preflight.json` |
| Measured run | `run_eval.py` | `output/eval_results.json` (+ checkpoint) |
| Summarise | `summarise_eval.py` | `output/eval_results.summary.json` |
| Analysis | `analysis.py` (Jupytext) | `analysis.ipynb` (gitignored) |

## Provenance

- Source commit, lockfile hash, and per-cell effective settings recorded in
  the runtime manifests at build time.
- Operator: a-build agent, 2026-09-15. Measured-run operator recorded in
  `output/eval_results.json`.

## Results

Measured run completed 2026-09-15 (a-build agent); preflight 14/14 PASS;
the freeze was verified immediately before the measured run
(`output/frozen.manifest.json` pins the pre-run inputs).

- Evidence recoverability: A = 0.000 (by construction), B = 0.792, C = 1.000.
- Evidence Recall@10: B = 0.583, C = 0.792; MRR@10: B = 0.552, C = 0.698.
- Paired hit@10 delta (B−C): −0.208, bootstrap 95% CI [−0.375, −0.083]
  — the interval excludes zero. Four of five disagreements are
  parser-stage losses on Type B (WinAnsi without `/ToUnicode`)
  documents; one is a retrieval miss on fully recovered Type A evidence.
- Extraction speed still favours the chain: median held-out reader time
  3.9 s (B) vs 28.7 s (C).

Full results, discussion, and limitations: `report.md`. Per the decision
rule, production behaviour is unchanged by this experiment; any change
requires a separate OpenSpec proposal.
