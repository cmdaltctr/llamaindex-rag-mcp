# Experiment 33: OCR routing natural-positive study

**ID**: `33-ocr-routing-natural-positive-2026-09-17`
**Date planned**: 2026-09-17
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED — protocol frozen; corpus and labels not yet frozen
**Relation**: OpenSpec change `experiment-33-ocr-routing-natural-positive`; Experiments 29, 30, 31; ADR-065, ADR-066, TDR-024
**Machine-readable plan**: [`plan.json`](plan.json) (the plan wins if this file and the plan disagree)

## Why this experiment exists

Experiment 29 promoted the OCR routing gate (`OCR_FALLBACK_ENABLED=true`,
`0.5` confidence, `0.10` page fraction). Its held-out set had no document
that needs OCR, so held-out recall was never measured. The one recall check
was a single development scan (Kerr 1998).

This study measures the shipped gate on natural documents that need OCR and
natural documents that do not. It does not change the gate.

**In plain terms:** when a real scanned PDF arrives, does the shipped
pipeline send it to OCR? And does it leave healthy PDFs alone?

## Research questions

```
Q1 (primary, safety). How many natural held-out documents that need OCR
   does the shipped gate keep on the fast path? (false_negative_count,
   routing recall with a Wilson 95% interval)

Q2 (secondary, cost). How many natural held-out documents with a usable
   text layer does the gate send to OCR, and how many OCR pages does
   that waste? (false_positive_count, unnecessary_ocr_pages)

Q3 (secondary, attribution). Where the fast path loses text on a
   correctly routed document, which reader tier lost it?
   (reader_quality_loss — never counted as an OCR false negative)
```

This is a measurement study with preregistered triggers, not a pass/fail
gate. See "Decision rule".

## Background and prior evidence

- Experiment 29: safety gate PASS; recall `not_evaluable` on held-out data.
- Experiment 30: the reader fallback chain rescues silent-empty PDFs.
- Experiment 31: LiteParse rescues Type B WinAnsi text by character count
  but loses most of its content. This is reader-quality loss.
- The routing decision depends on the reader chain: a successful rescue sets
  `pages_needing_ocr` to 0 (TDR-024). A replay of raw classifier output is
  therefore not the shipped policy. Experiment 29 routed Sloman wrongly for
  this reason.

## Measured policy

The policy under test is the packaged default. Nothing is replayed.

| Item | Value |
| --- | --- |
| `OCR_FALLBACK_ENABLED` | `true` |
| `OCR_FALLBACK_MIN_CONFIDENCE` | `0.5` |
| `OCR_FALLBACK_PAGE_FRACTION` | `0.10` |
| Unconditional types | `scanned`, `image_based` |
| Reader | `pdf_inspector` with fallback chain liteparse → pypdf |
| Code path | `core.ingestion.backends.local.read_documents` → `build_pdf_reader` → `OcrRoutedPdfInspector` |
| OCR client | `None` (no worker) |

`route.py` calls the production `read_documents` function. The seam stamps
`ocr_required` on the document. The harness reads that value.

## Corpus

### Strata

| Stratum | Definition | Expected label |
| --- | --- | --- |
| `born_digital` | PDF made from a digital source | usable |
| `mixed` | Mostly born-digital, with some scanned or image-only pages | either |
| `image_only_scan` | Scan with no text layer | needs_ocr |
| `scan_with_text_layer` | Scan with an existing OCR text layer, faithful or junk | either |
| `reader_failure` | Usable text layer that pdf-inspector extracts as empty | usable |

The stratum comes from provenance at sourcing. The label decides routing
correctness. The stratum never does.

### Sampling rules

1. Target 8 documents per stratum.
2. Include at least 3 unrecoverable pages or documents across the corpus.
3. Accept documents with 100 pages or fewer.
4. Accept only these licences: public domain, US government work, CC0,
   CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA.
5. Reject a candidate whose SHA-256 is in `dev_exclusions.json`
   (Experiments 29, 30, 31). Reject the Experiment 31 source identifiers.
6. Do not run pdf-inspector on candidates for `born_digital`, `mixed`,
   `image_only_scan` or `scan_with_text_layer` before the Stage A run.
   Select them from provenance, poppler output and the labelling tools.
7. Select `reader_failure` candidates with raw `pdf_inspector.process_pdf`
   (`text_based`, empty markdown), as Experiment 31 did. This is part of the
   stratum definition and is disclosed.
8. Record every document in `sources.json`: title, year, source URL,
   licence, stratum, page count, SHA-256. `SOURCING.md` is generated from it.

**Deviation from `tasks.md` 2.8:** the task names `corpus/SOURCING.md`.
`experiments/**/corpus/` is gitignored, so the log lives at the experiment
root, where it is committed.

**Scope limit:** the 100-page cap excludes long books. The long-book false
route from Experiment 28 stays a development regression case (Experiment 29).
This study makes no claim about documents longer than 100 pages.

**Split:** every natural document is held-out. Synthetic documents (tasks
section 5) are a separate stratum and never enter held-out measurements.

## Ground truth (task 1.1)

Labels come from an independent page assessment. pdf-inspector output and
routing output never decide a label.

### Evidence per page

1. Render the page with poppler `pdftoppm`: 150 dpi, 1600 px long side, PNG.
2. Extract the text layer with poppler `pdftotext -layout` and with pypdf.
3. Get a reference transcription of the page image from a vision model via
   OpenRouter. Temperature 0. Output is JSON with
   `legibility` (`legible`, `illegible`, `no_text`) and `transcription`.

pypdf is also fallback tier 2 of the measured path. A text layer that any
independent extractor reads is a usable text layer, so this is disclosed and
accepted.

### Match score

Normalise text with NFKC and lowercase. Split on non-word characters. Drop
tokens shorter than 2 characters. `R` is the multiset token recall of the
text layer against the reference transcription. `R_best` is the higher `R`
of the two extractors.

### Page rule

| Condition (first match wins) | Page label |
| --- | --- |
| `legibility == illegible` | `unrecoverable` |
| Reference has fewer than 10 tokens | `usable` (no text) |
| Call failed after 3 attempts, or output truncated | `ambiguous` |
| `R_best >= 0.80` | `usable` |
| `R_best < 0.50` | `needs_ocr` |
| Otherwise | `ambiguous` |

A junk OCR text layer scores a low `R_best` and is `needs_ocr`. Character
count alone never decides a label.

### Document rule

| Condition (first match wins) | Document label |
| --- | --- |
| Unrecoverable pages ≥ 50% of pages | `unrecoverable` |
| `needs_ocr` pages / pages ≥ 0.10 | `needs_ocr` |
| (`needs_ocr` + `ambiguous`) pages / pages < 0.10 | `usable` |
| Otherwise | `ambiguous` |

The 10% tolerance is the missing-page tolerance approved in the Experiment 29
decision register. It equals the gate threshold by operator judgement. This
is disclosed.

### Operator spot check and label freeze

1. Review every `unrecoverable` page against its image.
2. Review every page of every `ambiguous` document.
3. Review a seeded (seed 33) 10% random sample of the remaining pages.
4. Record each verdict in `spot_check.json`.
5. Freeze the labels only when disagreement on the random sample is 10% or
   less.

If disagreement is above 10%, revise the page rule and repeat the spot check.
This is allowed because no routing output exists yet. Record the revision in
`plan.json` amendments.

## Measurements (task 1.3)

The population is natural held-out documents labelled `needs_ocr` or
`usable`. Every definition below is fixed before any routing output exists.

### Primary

| Measurement | Definition |
| --- | --- |
| `routing_recall` | routed `needs_ocr` documents / `needs_ocr` documents, Wilson 95% interval |
| `false_negative_count` | `needs_ocr` documents with `ocr_required == false` |
| False-negative detail | Stratum, `pdf_type`, confidence, `pages_needing_ocr`, `needs_ocr` page count (evidence at risk) |

### Secondary

| Measurement | Definition |
| --- | --- |
| `routing_precision` | routed `needs_ocr` documents / routed documents |
| `false_positive_count` / rate | `usable` documents routed; rate over `usable` documents |
| `unnecessary_ocr_pages` | `usable` pages inside routed documents |
| `projected_ocr_seconds` | routed pages × 33.7 s (best) and × 106.4 s (worst). PROJECTION |
| By stratum | Confusion counts per stratum |
| Ambiguous sensitivity | Primary counts with `ambiguous` documents as `needs_ocr`, then as `usable` |
| Unrecoverable routes | Routing decision per `unrecoverable` document, outside every denominator |
| `reader_quality_loss` | Fast-path documents whose extracted text scores token recall < 0.80 against the reference transcription of legible pages. Attributed to `extraction_fallback_backend` when set, else to pdf-inspector |

### Monitored

- `read_seconds` per document.
- Content-type detection label and detector path (Magika version or suffix
  fallback).

## Stages (task 3.4)

| Stage | Scope | Authorised |
| --- | --- | --- |
| A | Routing only. `ocr_client=None`. No worker, no model, no network in `route.py` | Yes, after the corpus and label freeze |
| B | Real PaddleOCR-VL on a named subset | **No.** Needs a separate decision-register entry naming the subset, timeout and runtime budget |

`route.py` has no code path that starts an OCR worker. Stage B gets its own
script after authorisation.

## Decision rule

| Outcome | Interpretation |
| --- | --- |
| Zero natural held-out `needs_ocr` documents | INCOMPLETE. Held-out recall is not claimed |
| `false_negative_count >= 1` | Material finding. Recommend a separate calibration proposal |
| `false_positive_count >= 1` on `born_digital` | Material finding. Recommend a separate calibration proposal |
| Neither trigger | The gate has direct natural-positive recall evidence on this corpus, with the stated interval |

The `0.5` and `0.10` thresholds never change in this experiment.

## Privacy and secrets

- The PDFs are public open-licence files and are never committed.
- `OPENROUTER_API_KEY` is read from the environment by `label_pages.py` only.
  It is never written to any artefact. `route.py` runs in a process without it.
- Manifests record backend names, versions and content hashes only.

## Procedure

```bash
EXP=experiments/33-ocr-routing-natural-positive-2026-09-17
# 1. Sourcing: fill sources.json, then download and verify
uv run python $EXP/prepare_corpus.py
# 2. Labelling: cost probe on 20 pages, then all pages
uv run python $EXP/label_pages.py --limit-pages 20
uv run python $EXP/label_pages.py
uv run python $EXP/build_labels.py
# 3. Operator spot check -> spot_check.json, then freeze
uv run python $EXP/freeze.py
# 4. Stage A
uv run python $EXP/route.py
uv run python $EXP/summarise_eval.py
```

## Artefacts expected

| File | Description | Committed |
| --- | --- | :-: |
| `protocol.md`, `plan.json` | Preregistration | ✅ |
| `dev_exclusions.json` | Development digests (Experiments 29 to 31) | ✅ |
| `sources.json`, `SOURCING.md` | Corpus provenance and licences | ✅ |
| `labels.json`, `spot_check.json` | Frozen labels and operator review | ✅ |
| `output/frozen.manifest.json` | Freeze digests | ✅ |
| `output/runtime_manifest.json` | Policy identity, versions, detection path | ✅ |
| `output/routing.json` | Per-document Stage A rows | ✅ |
| `output/eval_results.summary.json` | Measurements | ✅ |
| `report.md` | Result report | ✅ |
| `corpus/`, `output/.pages/`, `output/.transcripts/` | PDFs, renders, transcriptions | local only |
