# Experiment 33 handoff — remaining work across three worktrees

Written 2026-09-17 after Stage A. Paste the prompt below into a fresh agent
session. Everything it needs is committed; nothing depends on chat history.

---

You are continuing Experiment 33 in the OMRG repository. Three git worktrees
are involved and they are interconnected. Read
`experiments/33-ocr-routing-natural-positive-2026-09-17/report.md` and
`protocol.md` first, then `plan.json` (amendments and decision register).

## Worktrees and their state

| Worktree (sibling of the main checkout) | Branch | State |
| --- | --- | --- |
| `llamaindex-rag-mcp-feat-experiment-33-ocr-routing-natural-positive` | `feat/experiment-33-ocr-routing-natural-positive` | Experiment 33. Labels and corpus frozen. Stage A done on both arms. Report written. **Work here by default.** Not pushed |
| `llamaindex-rag-mcp-feat-full-page-ocr-evidence` | `feat/full-page-ocr-evidence` | Draft PR #95 (`7280766`), TDR-026. Local CI green. Waiting on the Stage A verdict, which now exists |
| `llamaindex-rag-mcp-feat-page-level-ocr-routing` | `feat/page-level-ocr-routing` | OpenSpec change `page-level-ocr-routing`, planning artefacts only (`3d2da73`). Not pushed. Implementation waits on task 6.7 evidence |
| `llamaindex-rag-mcp-v3` | `v3` | Integration branch. Clean. PRs target it |

Never check out `feat/full-page-ocr-evidence` inside another worktree. Stage A
read its code through a temporary detached worktree:

```bash
git worktree add --detach ../llamaindex-rag-mcp-exp33-arm-candidate 7280766
# ... run ...
git worktree remove ../llamaindex-rag-mcp-exp33-arm-candidate
```

## Stage A result you are acting on

Frozen labels: 18 documents need OCR, 22 do not (1,123 pages, 40 PDFs).

| Arm | Recall | False negatives | False positives | Routed pages |
| --- | ---: | ---: | ---: | ---: |
| `sampled_baseline` (`5bac71e`) | 0.556 (10/18) | 8 | 1 (`mx08`) | 395 |
| `full_scan_candidate` (`7280766`, PR #95) | 0.611 (11/18) | 7 | 1 (`mx08`) | 444 |

Three miss mechanisms: 8-page detection sampling (`tl02`, fixed by PR #95);
pdf-inspector's page test missing scanned pages that carry a header line or
junk OCR text (`mx02`, `mx07`, `tl07`, `tl08`) plus the ADR-066 rescue zeroing
evidence after recovering junk (`rf06` fast-path recall 0.236, `rf07` 0.469);
and equation loss the gate never looks at (`bd04`).

## Work remaining, in order

### 1. Task 6.7 — local OCR tier measurement (Experiment 33 worktree)

Evidence gate 1 for `page-level-ocr-routing`. Operator approved it on
2026-09-17; the subset, 900 s per-document soft timeout and 3600 s runtime
budget are in `plan.json` `decision_register`. Local only, no cloud, no
PaddleOCR-VL.

```bash
cd ../llamaindex-rag-mcp-feat-experiment-33-ocr-routing-natural-positive
E=experiments/33-ocr-routing-natural-positive-2026-09-17
V=$(pwd)/.venv/lib/python3.12/site-packages
PDFIUM_LIB_PATH=$V/liteparse/libpdfium.dylib \
ORT_DYLIB_PATH=$V/onnxruntime/capi/libonnxruntime.1.28.0.dylib \
PYTHONUNBUFFERED=1 uv run python $E/local_ocr.py
```

It refuses to run unless the labels are frozen and the freeze verifies. It
writes `output/local_ocr/pages.json` and `summary.json`: token recall against
the reference transcription, confidence calibration, escalation share at
confidence cuts 0.5 to 0.9, hosted-recommended share, seconds per page.
First run downloads a 31 MB PP-OCRv6 model into `output/.pdfi_models`.

Then tick task 6.7 in
`openspec/changes/experiment-33-ocr-routing-natural-positive/tasks.md`, add the
numbers to `report.md`, and commit.

### 2. Page-level proposal evidence gate (page-level worktree)

Take the task 6.7 numbers to `feat/page-level-ocr-routing`, fill tasks 1.1 and
1.2 of change `page-level-ocr-routing` with them, and record go, rework or
stop in its `design.md`. Rough decision guide, to confirm with the operator:
local OCR is worth a tier if most `needs_ocr` pages reach token recall ≥ 0.8
and its confidence signal separates the failures it cannot read.

### 3. PR #95 decision (full-page-ocr-evidence worktree)

Stage A evidence now exists: +1 document caught, no new false alarm, 49 extra
OCR pages, 0.24 s extra read time over 40 documents, and the TDR-026
illustrated-book risk did not appear. Recommend merge to the operator, then:

```bash
cd ../llamaindex-rag-mcp-feat-full-page-ocr-evidence
gh pr ready 95        # after the operator agrees
gh pr merge 95 --squash --base v3
```

Update `docs/tdr/026-pdf-inspector-sampled-ocr-evidence.md` status from
Proposed to Accepted with the Stage A numbers, then archive the OpenSpec
change (`/opsx-archive full-page-ocr-evidence`). After the merge, rebase the
Experiment 33 branch on `v3`.

### 4. Extraction-quality comparison (Experiment 33 worktree)

The operator's first spot check judged pypdf's text, not the pipeline's, so
their column, table and structure notes do not yet describe pdf-inspector.
Stage A saved the real fast-path text in
`output/arm_*/.extractions/<doc_id>.txt`. Compare pdf-inspector's output with
pypdf against `understanding_label` and the notes in `spot_check.json`,
focusing on the pages the operator flagged for two or three columns, tables,
headings and footnote numbers. One known example: on the clean two-column
IEEE paper `corpus/synthetic/clean/2401.00632.pdf`, pdf-inspector keeps column
order but fuses a table with the figure beside it.

Then ask the operator which they want for column and table fallback: extend
`page-level-ocr-routing` with a "tables or columns detected" escalation, a
separate proposal, or measure more first.

### 5. Rescue-quality proposal (new change)

`report.md` conclusion item 2. The ADR-066 rescue zeroes `pages_needing_ocr`
after recovering text, and on `rf06` and `rf07` the recovered text matched only
24% and 47% of the page. Propose a quality signal so a junk rescue counts as
OCR-required. New worktree, new OpenSpec change, PR to `v3`.

### 6. Experiment 33 ADR and archive (Experiment 33 worktree)

Write the ADR in `docs/adr/` (next number after 068) using the `s-adr` skill.
It must state **prominently**, at the operator's explicit request:

1. Extraction that keeps the words can still fail understanding. The operator's
   recurring cases: equations and scientific notation, figures and charts
   needing interpretation, two- and three-column layout, tables, headings,
   footnotes and sidebars, old-book spelling, and non-Latin scripts (Hindi,
   Arabic). They are recorded as `understanding_label` and notes in
   `spot_check.json`.
2. Task 5.3, the print-and-rescan tier, was skipped by operator decision on
   2026-09-17, so real physical scan artefacts (page curl, uneven lighting,
   bleed-through, paper texture) are untested.
3. The label validation history: the automatic rule disagreed with the operator
   on 41.5% and then 20.2% of the random sample, and the final labels take the
   operator's verdict on the 277 reviewed pages and the rule on the other 846.

Then run `openspec validate --all --strict`, `./scripts/local_ci.sh`, open a PR
to `v3`, and archive the change with `/opsx-archive`. Before removing any
worktree, follow Critical Gotcha #15 in `CLAUDE.md`: copy the gitignored
`output/` artefacts (labels, transcripts, page images, extractions) to the
target worktree first.

## Still unauthorised

Stage B with PaddleOCR-VL (tasks 6.1 to 6.6) needs a separate operator
decision naming the document subset, timeout and runtime budget. Do not run it.

## Guardrails

1. `labels.json` and the corpus are frozen. Never edit a label. Run
   `uv run python $E/freeze.py --check` before any measurement.
2. Thresholds `0.5` and `0.10` do not change in Experiment 33. Recalibration
   needs its own proposal.
3. OpenRouter is used only for labelling, and labelling is finished.
4. Experiment PDFs, page images, transcripts and extractions are gitignored.
   Keep it that way.
