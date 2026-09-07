# PDF Baseline Fixtures (improve-rag-input-quality-5, tasks 1.1 and 1.2)

Compact, hand-built PDF fixtures that pin the current `pdf-inspector`
baseline before the OCR routing work lands in stage 2.

## Licence

All fixture content is self-authored for this repository. No third-party
material, no derived works, no licence obligations beyond the project
licence. Safe to commit.

## Calibration vs evaluation disjointness

The two sets below are **disjoint by design** (design D7.2):

- **Calibration** — used to choose the OCR routing gate (confidence
  threshold, `pages_needing_ocr` proportion) in task 1.7. Never used for
  Stage 5 quality claims.
- **Evaluation** — held out from calibration entirely. Used only for the
  Stage 5 ablation (task 5.1).

| Set         | File                                  | Intended content class            |
| ----------- | ------------------------------------- | --------------------------------- |
| calibration | `calibration/cal_clean_text.pdf`      | clean single-column text          |
| calibration | `calibration/cal_table_text.pdf`      | table-like positioned text        |
| calibration | `calibration/cal_scanned.pdf`         | scanned page (no text layer)      |
| evaluation  | `evaluation/eval_clean_text.pdf`      | clean single-column text          |
| evaluation  | `evaluation/eval_two_column.pdf`      | two-column text on one page       |
| evaluation  | `evaluation/eval_scanned.pdf`         | scanned page (no text layer)      |
| evaluation  | `evaluation/eval_image.pdf`           | image-only page (no text layer)   |
| evaluation  | `evaluation/eval_mixed.pdf`           | mixed: text page + image-only page |

`manifest.json` is the machine-readable record of this split and of the
observed `pdf-inspector` classification per file. The tests in
`tests/unit/test_pdf_baseline_fixtures.py` assert that the manifest and
the files on disk stay in agreement.

## Observed baseline (recorded 2026-09-06)

Observed with the locked `pdf-inspector` version via
`pdf_inspector.process_pdf`:

- Text fixtures classify `text_based` at confidence 1.00; the positioned
  "table" rows are flattened onto one markdown line (structure loss the
  OCR work must not regress further).
- The two-column page classifies `text_based` at confidence 1.00, and the
  emitted markdown interleaves the columns line by line, losing reading
  order and whitespace (`corpus.must` join). Layout damage alone does not
  flip the classification — which is why task 2.5 keeps text-based
  multi-column PDFs on the fast path.
- Pages with no text operators classify `scanned` at confidence 0.90 with
  `pages_needing_ocr == [1]` and no markdown (the library returns `None`;
  the adapter normalises it to the empty string). The image-only page also
  reports `scanned` in this build; there is no distinct `image_based`
  observation to pin.
- The mixed document (text page + image-only page) classifies
  `text_based` at confidence 0.50 with `pages_needing_ocr == []`, and its
  markdown silently contains only page one. The current classifier does
  not flag the blank second page — this gap is the recorded degraded
  behaviour that motivates the routing seam and the `pages_needing_ocr`
  scalar in task 2.10.

Re-run the probe tests after any `pdf-inspector` version bump: a diff
against these pins is the visible baseline change.
