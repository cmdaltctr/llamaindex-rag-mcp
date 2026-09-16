# Design: Experiment 31 Reader Rescue Retrieval Impact

## Context

The current PDF path uses `pdf-inspector` first. When a text-based PDF reports an empty extraction, OMRG can retry with LiteParse with OCR disabled and then pypdf. Experiment 30 validated text recovery and cost on known failures. It did not test retrieval impact.

The fallback chain is hard-coded in the production `pdf-inspector` reader. No setting disables it or selects a single tier. Cells that differ from production therefore need script-local reader mirrors, as Experiment 30 used.

A rescue resets the `pages_needing_ocr` count to zero. Without a rescue, the flagged count remains, and the OCR routing gate (enabled by default) can dispatch the PDF to the OCR worker.

## Goals

- Confirm that rescued text survives chunking and embedding well enough to retrieve gold evidence.
- Measure whether the LiteParse-first chain retrieves gold evidence as well as a pypdf-only rescue.
- Keep all non-reader variables fixed.
- Preserve full experiment provenance and negative results.

## Non-Goals

- Do not recalibrate OCR routing.
- Do not compare text-layer rescue against OCR.
- Do not compare embedding models.
- Do not change the reader fallback order.
- Do not promote or remove a production default from this experiment alone.

## Experimental Cells

### Cell A: sanity check

Use `pdf-inspector` extraction only, through a script-local mirror. Do not invoke LiteParse or pypdf rescue when extraction is empty.

Every held-out PDF must produce zero chunks in this cell. Cell A verifies the harness and the trigger. It is not a measured comparison, because its retrieval score is zero by construction. Healthy distractors keep their chunks in this cell; only the silent-empty held-out set must stay empty.

### Cell B: candidate

Use the current production chain:

`pdf-inspector -> LiteParse with OCR disabled -> pypdf`

### Cell C: reference

Use a script-local mirror of the historical pypdf-only guard (commit 928f030), as in Experiment 30:

`pdf-inspector -> pypdf`

All cells continue through the same current chunking, embedding, vector-store, retrieval, and reranking path. Cell B against Cell C is the measured comparison.

## Corpus

Use three groups:

1. Development/regression group: the known pathological documents from Experiment 30 and related documented failures.
2. Held-out group: independently selected natural PDFs that meet the inclusion rule below.
3. Distractor group: 10-20 fixed healthy text-based PDFs where the rescue does not fire.

The held-out and distractor groups must be frozen before measured scoring. Documents inspected while designing or debugging the candidate do not count as held-out evidence.

### Inclusion rule

A held-out PDF must meet the exact production rescue trigger:

- `pdf-inspector` classifies it as `text_based`;
- it has at least one page;
- `pdf-inspector` returns an empty extraction (`markdown == ""`).

Exclude PDFs with partial or whitespace-only extraction, because the rescue does not fire on them. Record the count of excluded partial extractions found during sourcing.

### Sample target

Experiment 28 found one silent-empty PDF in 79 real library documents, so natural cases are rare. Source candidates from collections known to carry these failures, such as Internet Archive scanned books with a `GlyphLessFont` text layer.

Target at least 5 held-out PDFs and 20-30 queries. Record the failure type of each PDF (for example IA `GlyphLessFont`, WinAnsi without `/ToUnicode`). The report must state which failure types the result covers.

## Index Composition

Build one index per cell. Each index contains the held-out group and the distractor group.

The rescue does not fire on distractors, so every cell extracts them identically. They give the held-out queries competing documents without adding a new variable. Do not index development documents in measured indexes.

## Gold Evidence

Each measured query must identify answer-supporting evidence in the source PDF independently of the reader output. Gold evidence must not be created from any experiment cell's extracted text.

### Evidence matching

Qrels store gold evidence as text spans, not chunk identifiers. Chunk identifiers differ between cells because each cell extracts different text.

Freeze one matching rule before measured runs and use it for both evidence recoverability and retrieval hits:

- fold case;
- collapse whitespace and line breaks;
- rejoin words split by end-of-line hyphens;
- accept a match at or above a frozen fuzzy-match threshold.

A retrieved chunk is a hit when it matches the gold span under this rule.

## Metrics

Primary measurements:

- gold-evidence recoverability before embedding;
- Evidence Recall@1, @3, @5, and @10;
- MRR@10;
- no-hit rate.

Secondary measurements:

- extraction latency;
- chunk count;
- embedding request tokens;
- index size when available.

The report must present paired per-query results for Cell B against Cell C. Report a paired bootstrap confidence interval on the per-query difference only when there are at least 20 measured queries. Small samples must be reported as small samples rather than converted into strong general claims.

## Validity Controls

- Freeze corpus, distractors, queries, qrels, matching rule, and query order before measured runs.
- Use the `documents` profile in all cells, because reranker settings differ between profiles.
- Use the same embedding provider/model identity in all cells.
- Use the same tokenizer, chunker, retrieval settings, vector store, and reranker settings in all cells.
- Disable the OCR worker in all cells (`OCR_WORKER_COMMAND` empty). Record `ocr_required` and `ocr_used` for each document.
- Record source commit, lockfile hash, effective settings, and index identity.
- Abort a measured cell when a controlled variable differs unexpectedly, or when any measured document reports `ocr_used=True`.

## Decision Rule

This experiment produces evidence about the existing fallback chain. It does not directly change production behaviour.

If rescued evidence is recoverable but retrieval misses it, retain the result and investigate retrieval separately. If Cell B retrieves materially worse than Cell C, open a separate change before altering the fallback order.
