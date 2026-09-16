# Experiment: Misnamed-extension content detection

**ID**: `32-misnamed-extension-detection-2026-09-16`
**Date**: 2026-09-16
**Operator**: AI agent (for Dr Muhammad Aizat Bin Md Hawari)
**Status**: PASS
**Verdict**: Content-based detection ignores lying extensions — ADR-068 claim holds at corpus scale.
**Change**: `pin-magika-detection`; evidence for ADR-068 (verification section).

---

## Bottom line

Every one of the 30 misnamed copies kept its content-true Magika
label. All 19 real PDFs renamed to `.py`, `.md`, or `.txt` still
detected as `document/pdf`. All 11 Python, Markdown, and text files
renamed to `.pdf` kept `code/python`, `document/markdown`, or
`document/text`. The two true-named baselines matched end to end.
The suffix fallback map was wrong for every misnamed file, which is
the exact failure Magika removes.

## Context

ADR-068 pinned `magika==1.0.3` and fixed the CLI result parser. Its
misnamed-file evidence was two ad-hoc probes. This experiment scales
that evidence to the full Experiment 31 corpus (8 held-out
silent-empty PDFs: 6 IA GlyphLessFont, 2 ACL WinAnsi; 11 healthy
distractors) plus the pin gate's 11 text and code files.

## Results

| Set | Files | Smoke exit | Result |
| --- | ----- | ---------- | ------ |
| baseline_pdf (true names) | 19 | 0 | 19/19 all-match |
| baseline_text (true names) | 11 | 0 | 11/11 all-match |
| swap_pdf_names (PDFs as `.py`/`.md`/`.txt`) | 19 | 1 | every Magika label `document/pdf`; suffix map wrong on all 19 |
| swap_text_to_pdf (text/code as `.pdf`) | 11 | 1 | every Magika label content-true; suffix map said `document/pdf` on all 11 |

Gates G1 to G5 all PASS (see `output/summary.json`). Whole-run
detection cost per set: 0.44 s, 0.88 s, 0.24 s, 0.22 s. Exit 1 on
the swap sets is the smoke tool reporting the label shift, not a
detection failure. No fallback, timeout, or detector error occurred.

Sample rows (from `output/swap_*.json`):

```
doc00.py   suffix=code/python       magika=document/pdf
doc01.md   suffix=document/markdown magika=document/pdf
file00.pdf suffix=document/pdf      magika=code/python
```

At ingestion this means the renamed PDFs would skip the PDF readers
only if their content were binary (it is not: `document/pdf` stays
readable), and the text files behind `.pdf` names route to the AST
splitter or Markdown parser instead of a PDF reader.

## Discussion

The pathological PDFs matter most: the six IA GlyphLessFont and two
ACL WinAnsi files that motivated Experiment 31 are structurally
normal PDFs, so the detector reads their container, not their broken
text layers. All eight kept `document/pdf` under lying names. The
result is bounded by the same limits ADR-068 records: very short
files can lose their code label (pin-gate tiny-source diagnostic),
and no ingest or retrieval was run here — routing correctness at
ingestion follows from the label, not measured in this experiment.

## Conclusion

Detection under the pin is extension-independent on this corpus.
ADR-068's verification section now cites this experiment. Nothing in
production changed; no rerun of Experiment 31 was made or is needed.

## Artefacts

- `protocol.md` — gates and predesignated ground truth (written
  before any run)
- `build_swaps.py`, `output/swap_manifest.json` — deterministic
  copies with sha256 and expected labels
- `run_detection.py`, `output/<set>.json` — per-set payloads, exit
  codes, elapsed times
- `summarise_eval.py`, `output/summary.json` — gate evaluation
- `analysis.py` — pandas label tables (Jupytext percent format)
