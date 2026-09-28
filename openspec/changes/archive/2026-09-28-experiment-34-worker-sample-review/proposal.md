# Experiment 34: Worker Sample Review on Real Documents

## Why

PaddleOCR-VL, the isolated OCR worker, has never been measured on the
corpus documents it exists for. Experiment 33's Stage B was deferred, so
every statement about worker quality on this corpus is inference, not
measurement. Three named issues wait on that evidence:

1. **Old books (`io06`).** The local OCR tier reads early-modern
   typography at median recall 0.609 while reporting median confidence
   0.922, so the page unit keeps confidently-wrong text. Whether the
   worker reads these pages well, including their heading structure, is
   unknown. The operator's spot-check notes on `io06` pages read "needs
   support for language".
2. **Triple-column pages with images (`io04`).** The operator's note
   "needs support for dual/triple column and images needs llm maybe"
   points at exactly the worker's layout understanding, which is
   unmeasured.
3. **Two-column and table pages** (`bd01` p4, `bd02` p1, `tl03` p5).
   Two-column reading order was fixed and measured on the LiteParse
   path (0.5309 → 0.9613, PR #96); whether the worker preserves the
   same pages' structure in Markdown is unmeasured.

This is the operator's decision to authorise a bounded worker run: a
small sample, reviewed by eye, before any larger experiment or any fix
work (the deferred task 2.3 signal hunt depends on knowing what the
worker actually produces).

## What Changes

- Add Experiment 34 under `experiments/34-worker-sample-review-2026-09-19/`.
- Provision the OCR worker environment once (`ocr-worker/provision.py`,
  the multi-GB Paddle install the smoke test gates behind operator
  approval).
- Run the worker over a frozen sample of at most 50 pages drawn from
  the Experiment 33 corpus (read-only; the corpus and labels stay
  frozen and untouched in the Experiment 33 worktree):
  - `io06` — 12 pages, including the operator's eight spot-checked pages;
  - `io04` — 12 pages, including the four spot-checked pages;
  - `bd01` (4, incl. p4), `bd02` (4, incl. p1), `tl03` (4, incl. p5);
  - one clean modern-print control document — 6 pages.
- Emit one self-contained review page per run: original page image on
  the left, worker Markdown on the right, and a checklist the operator
  fills in per page (text accuracy, column order, headings, table
  readability, ready-for-an-LLM, plus a note field). Choices persist to
  a JSON verdicts file.
- Report the operator's verdicts, not automatic scores. Automatic
  scoring against the reference transcriptions is out of scope; the
  point is to see the worker's actual output with human eyes.

## Runtime budget (operator decision, 2026-09-19)

- Sample cap: 42 pages as listed, never more than 50.
- 900-second soft timeout per document, as in Experiment 33.
- 2-hour wall-clock cap on the worker run, checkpointed per document so
  a stop resumes cleanly.

## Impact

- Code: none. The worker speaks protocol 1.1 already merged on the base
  branch; the harness drives it through the existing client.
- Data: reads the Experiment 33 corpus by absolute path from its
  worktree; the Experiment 33 worktree must survive until this review
  completes.
- Evidence: the verdicts decide whether task 2.3 (the old-book signal
  experiment) proceeds and what it should measure, and give the worker
  its first measured standing on this corpus.
