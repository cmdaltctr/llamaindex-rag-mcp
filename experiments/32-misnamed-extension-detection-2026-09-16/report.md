# Experiment 32: Content detection when file extensions lie

**ID:** `32-misnamed-extension-detection-2026-09-16`
**Date:** 2026-09-16
**Status:** PASS (gates G1 to G5)
**Evidence for:** ADR-068 — Magika content-type detection (`magika==1.0.3`, CLI transport)

## Question

Ingestion routes every file by `content_type` before any reader runs. Production
gets that label from Magika 1.0.3, run as a CLI subprocess, with the JSONL
output (`result.value.output.group/label`) parsed and normalised at the
boundary. The alternative is suffix routing: trust the file extension. The two
disagree exactly when a file name lies about its bytes, and then suffix routing
misroutes. A PDF named `notes.py` lands in the AST code splitter and produces
garbage chunks; a Python file named `report.pdf` lands in a PDF reader and
produces nothing.

This experiment tested whether the pinned detector keeps the correct
`content_type` label on every file when the extension contradicts the bytes.

## Method

Corpus, drawn from frozen earlier work:

- 19 PDFs from experiment 31: 8 silent-empty documents (6 IA GlyphLessFont
  scans, 2 ACL WinAnsi without `/ToUnicode` maps) plus 11 healthy distractors.
- 11 text and code files from the pin-gate acceptance corpus: 4 Python
  (`.py`), 4 Markdown (`.md`), 3 plain text (`.txt`).

Procedure: `build_swaps.py` made byte-identical copies (sha256 per file in
`output/swap_manifest.json`). PDF copies received a rotating lying extension
(`.py`, `.md`, `.txt`, index modulo 3). Text copies were renamed `.pdf`.
Detection ran through `scripts/magika_label_smoke.py`, the same detection
surface production calls (`detect_file_types`). Detection only: no ingestion,
no embedding, no store writes, originals untouched.

## Results

| Set | n | Magika labels | Suffix-map labels | Exit | Elapsed |
| --- | --- | --- | --- | --- | --- |
| `baseline_pdf` | 19 | `document/pdf` x19 | same | 0 | 0.42 s |
| `baseline_text` | 11 | `code/python` x4, `document/markdown` x4, `document/text` x3 | same | 0 | 0.86 s |
| `swap_pdf_names` | 19 | `document/pdf` x19 | `code/python` x7, `document/markdown` x6, `document/text` x6 | 1 | 0.28 s |
| `swap_text_to_pdf` | 11 | content labels unchanged | `document/pdf` x11 | 1 | 0.24 s |

Sample rows from `output/swap_*.json`:

```
doc00.py   suffix_label=code/python       magika_label=document/pdf
doc01.md   suffix_label=document/markdown magika_label=document/pdf
file00.pdf suffix_label=document/pdf      magika_label=code/python
```

Exit 1 on the swap sets is the smoke tool's mismatch flag: it fires when the
suffix map and Magika disagree (`would_change` on every swapped file). Here
every mismatch is the suffix map being wrong, never the detector.

Gate outcomes (`output/summary.json`): G1 `baseline_pdf_all_match` PASS;
G2 `baseline_text_all_match` PASS; G3 `renamed_pdfs_stay_document_pdf` PASS;
G4 `renamed_text_keeps_content_label` PASS; G5 `no_detector_failure` PASS
(zero fallbacks, zero timeouts, zero detector errors).

## Interpretation

Detection is extension-independent at this corpus scale: 30 of 30 misnamed
copies kept content-correct labels while the suffix map was wrong on all 30.

The 8 silent-empty PDFs kept `document/pdf` under lying names. Their text
layer is unreadable, but the container structure is valid PDF, and the
detector reads container signatures. So routing to the PDF reader chain
survives even for damaged files; what those readers then do with the broken
text layer is experiment 31's subject, not this one.

Downstream, the label is what ingestion dispatches on: `group == "code"`
routes to tree-sitter AST splitting, document groups route to the backend
chain. With content detection pinned, a lying extension cannot steer a file
into the wrong reader.

## Limits

1. Detection only. This proves the label, not chunk quality; routing
   correctness follows from the label contract already covered by ingestion
   tests.
2. Known weakness carried from the pin gate: very short files can lose a
   `code/*` label. ADR-068 records this.
3. Corpus bound: 19 PDFs and 11 repository text files. Images, archives, and
   office formats were not exercised.

## Artefacts

- `protocol.md` — hypothesis, corpus, and gates, written before the run
- `build_swaps.py`, `output/swap_manifest.json` — sha256-checked renamed copies
- `run_detection.py`, `output/<set>.json` — per-set payloads, exits, timings
- `summarise_eval.py`, `output/summary.json` — gate evaluation
- `analysis.py` — pandas label tables (Jupytext percent format)
