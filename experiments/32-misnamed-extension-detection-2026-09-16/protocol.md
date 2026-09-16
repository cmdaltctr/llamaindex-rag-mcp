# Protocol: Misnamed-extension content detection (Experiment 32)

**ID**: `32-misnamed-extension-detection-2026-09-16`
**Date**: 2026-09-16
**Operator**: AI agent (for Dr Muhammad Aizat Bin Md Hawari)
**Status**: PASS (5/5 gates)
**Change**: `pin-magika-detection` (evidence for ADR-068 verification)

## Purpose

Prove at corpus scale that the pinned Magika detector
(`magika==1.0.3`, subprocess CLI transport) labels files by content,
so an extension that lies cannot misroute ingestion. This extends
ADR-068's two-probe misnamed evidence to the full Experiment 31
corpus plus the pin gate's text corpus.

## Hypothesis

If detection is content-based, then renaming files to wrong
extensions leaves every Magika label unchanged, while the suffix
fallback map returns the lying extension's label. Baseline runs with
true names must all-match.

## Variables

| Type       | Variable              | Values                                   |
| ---------- | --------------------- | ---------------------------------------- |
| Independent | File extension        | true name vs swapped name (copies only) |
| Dependent  | Magika label, suffix label, smoke exit code | —              |
| Controlled | File bytes (sha256-identical copies), detector (`magika==1.0.3`), smoke tool, no ingest | — |

## Corpus and ground truth (written before any run)

Source A: all 19 real PDFs of the Experiment 31 corpus (8 held-out
silent-empty: 6 IA GlyphLessFont, 2 ACL WinAnsi; 11 healthy
distractors). Source B: the 11 non-PDF files of the pin gate corpus
(4 Python modules, 4 Markdown documents, 3 text documents). Originals
are never touched; working copies carry the swapped names.

| Set | Contents | Names | Expected Magika label | Expected smoke exit |
| --- | -------- | ----- | --------------------- | ------------------- |
| baseline_pdf | 19 PDFs | true `.pdf` | `document/pdf` each | 0 (all-match) |
| baseline_text | 11 text/code | true extensions | content-true (see below) | 0 (all-match) |
| swap_pdf_names | 19 PDFs | rotated `.py`/`.md`/`.txt` | `document/pdf` each | 1 (shift reported) |
| swap_text_to_pdf | 11 text/code | all `.pdf` | content-true (see below) | 1 (shift reported) |

Content-true labels (Set B, from the passing pin gate): `code/python`
(compose.py, pipeline.py, magika.py, codebase_map.py),
`document/markdown` (README.md, AGENTS.md, architecture.md,
ingestion.md), `document/text` (aurora, birch, bravo_harbour).

## Pass gates

- G1 baseline_pdf: 19/19 all-match, exit 0.
- G2 baseline_text: 11/11 all-match, exit 0.
- G3 swap_pdf_names: every Magika label `document/pdf` (19/19),
  exit 1, no detection error.
- G4 swap_text_to_pdf: every Magika label content-true (11/11),
  exit 1, no detection error.
- G5: no exit 2 (detector failure, fallback, empty input, or
  path-set defect) in any invocation.

A single wrong Magika label in G3 or G4 is a FAIL and a recorded
limitation for ADR-068. No repair, retry, padding, or threshold
change is permitted.

## Method

Detection only. `build_swaps.py` copies sources into
`output/work/<set>/` with swapped names and records sha256 in
`output/swap_manifest.json`. `run_detection.py` runs
`scripts/magika_label_smoke.py --json` once per set (and once per
baseline directory), saving payload, exit code, and elapsed time
atomically to `output/`. `summarise_eval.py` evaluates the gates and
writes `output/summary.json`. No ingest, store, embedding, or
collection operation runs at any point.

## Out of scope

Retrieval quality, reader behaviour on misnamed files, tiny-source
probes (covered by the pin gate diagnostics), and any rerun of
Experiment 31.
