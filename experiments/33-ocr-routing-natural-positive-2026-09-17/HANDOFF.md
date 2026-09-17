# Experiment 33 handoff — remaining work

Rewritten 2026-09-18 after task 6.7, the reader comparison, and the PR #95
merge decision. Everything below is committed; nothing depends on chat history.

## Worktrees: exactly two stay open

| Worktree (sibling of the main checkout) | Branch | Role |
| --- | --- | --- |
| `llamaindex-rag-mcp-feat-experiment-33-ocr-routing-natural-positive` | `feat/experiment-33-ocr-routing-natural-positive` | **Data and records.** The frozen corpus, page images, transcriptions, Stage A extractions and local OCR results live here and nowhere else. Every measurement runs from here |
| `llamaindex-rag-mcp-feat-page-level-ocr-routing` | `feat/page-level-ocr-routing` | **Code.** The LiteParse join-order fix and page-level-ocr-routing tasks 3 to 6 |
| `llamaindex-rag-mcp-v3` | `v3` | Integration branch. PRs target it |

Do not open a third worktree without asking the operator.

`feat/full-page-ocr-evidence` closes in queue item 1 and its worktree is
removed.

## Queue

1. **Merge PR #95** (`feat/full-page-ocr-evidence`). TDR-026 is Accepted with
   the Stage A numbers (`3b29bd0`); the OpenSpec change is archived and its
   pdf-reader delta synced into the main spec (`6ef9344`). Remaining: squash
   merge to `v3`, carry the data forward, remove the worktree.
2. **LiteParse join-order fix**, its own OpenSpec change on
   `feat/page-level-ocr-routing`. Scope and evidence gate below.
3. **`page-level-ocr-routing` tasks 3 to 6**, same branch. Already
   REWORK-approved: `OCR__LOCAL_MIN_CONFIDENCE = 0.8`, a script and typography
   pre-check before the local OCR tier, and the `io06` blind spot recorded as
   an accepted risk (confidence 0.922, recall 0.609).
4. **One PR to `v3`** covering items 2 and 3. Before opening it:
   `openspec validate --all --strict` and `./scripts/local_ci.sh`.
5. **Experiment 33 ADR, then archive the experiment.** The ADR must state
   **prominently**, at the operator's explicit request:
   1. The operator's understanding observations: equations and scientific
      notation, figures and charts needing interpretation, two- and
      three-column layout, tables, headings, footnotes and sidebars, old-book
      spelling, and non-Latin scripts (Hindi, Arabic). They are recorded as
      `understanding_label` and notes in `spot_check.json`.
   2. Task 5.3, the print-and-rescan tier, skipped by operator decision on
      2026-09-17, so real physical scan artefacts (page curl, uneven lighting,
      bleed-through, paper texture) are untested.
   3. The label validation history: the automatic rule disagreed with the
      operator on 41.5% and then 20.2% of the random sample, and the final
      labels take the operator's verdict on the 277 reviewed pages and the rule
      on the other 846.
6. **Later: a rescue-quality signal**, so a junk LiteParse rescue counts as
   OCR-required (`rf06` fast-path recall 0.236, `rf07` 0.469). `report.md`
   conclusion item 2. Its own change, after item 5.

## LiteParse join-order fix (queue item 2)

Scope:

1. The adapter in `src/omrg/integrations/pdf/liteparse.py` already labels each
   page `single`, `left` or `right` from text-item positions, then joins the
   items ignoring that label. Use the label when joining.
2. Per page, three cases: single column keeps today's order; multi-column
   re-sorts by column then position; table pages keep today's order until a
   table-aware order is measured separately.
3. Reject the naive 45% split. The measurement drops a journal front page to
   0.52 and a table page to 0.40.
4. No OCR, no worker and no routing change.

Why it matters beyond LiteParse: `rf04` is a rescued document, so the chain's
output is what retrieval sees, and it scored 0.53 reading order where plain
pypdf text scored 0.98 on the same pages. The operator's spot-check notes on
columns and tables judged pypdf text, not the pipeline, so this fix is the
first measurement of the real reading order.

Evidence gate before the PR, measured on the Experiment 33 reviewed pages:

- two-column body pages: reading-order score ≥ 0.90, up from 0.53
- no regression on `bd02` p1 (0.67) or `tl03` p5 (0.74)
- token recall unchanged, within ± 0.01
- scores reported per page class: single, multi-column, table

Measure it from **this** worktree, never the page-level one. Write the script
in `experiments/33-ocr-routing-natural-positive-2026-09-17/`, load the code
under test the way `route.py` does with `--code-root` pointing at the
page-level worktree, commit the script and its `output/*.json` here, and quote
the numbers in the proposal on the other branch.

## Results already in hand

Frozen labels: 18 documents need OCR, 22 do not (1,123 pages, 40 PDFs).

### Stage A routing (both arms)

| Arm | Recall | False negatives | False positives | Routed pages |
| --- | ---: | ---: | ---: | ---: |
| `sampled_baseline` (`5bac71e`) | 0.556 (10/18) | 8 | 1 (`mx08`) | 395 |
| `full_scan_candidate` (`7280766`, PR #95) | 0.611 (11/18) | 7 | 1 (`mx08`) | 444 |

Three miss mechanisms: 8-page detection sampling (`tl02`, fixed by PR #95);
pdf-inspector's page test missing scanned pages that carry a header line or
junk OCR text (`mx02`, `mx07`, `tl07`, `tl08`) plus the ADR-066 rescue zeroing
evidence after recovering junk (`rf06` fast-path recall 0.236, `rf07` 0.469);
and equation loss the gate never looks at (`bd04`).

### Task 6.7 local OCR tier

464 pages, 28 documents, 731 s, no error. 0.311 of body `needs_ocr` pages reach
token recall ≥ 0.8, 0.516 fall below 0.5, at 0.75 s median per page. Bimodal by
writing system: modern Latin-script print 0.977 median (0.840 ≥ 0.8), the 129
Devanagari and Arabic pages 0.000, handwriting 0.310, the early-modern Latin
book `io06` 0.609. Confidence separates (AUC 0.949); a 0.8 cut escalates 46.9%
and keeps 11.3% below 0.5 recall. `pages_recommending_hosted` fired on 6 of the
206 bad pages.

### Reader comparison (`output/reader_comparison.json`)

On the 41 reviewed pages labelled `usable`: `pdf_inspector` median recall 0.683
and order 0.683 with no text at all on 19 of 41; `liteparse` 0.991 and 0.982;
`pypdf` 0.990 and 0.964. Where pdf-inspector produces text it ties pypdf on
recall and equals or beats it on order. LiteParse keeps the words and loses the
order on multi-column pages, which is queue item 2.

## Data carry-over (CLAUDE.md Critical Gotcha #15)

Gitignored data moves forward by hand, before any worktree is removed:

```
feat/full-page-ocr-evidence -> feat/page-level-ocr-routing
feat/page-level-ocr-routing -> feat/experiment-33-ocr-routing-natural-positive
feat/experiment-33-...      -> llamaindex-rag-mcp-v3   (final home)
```

Carry the preserve class: `experiments/**/output/`, `experiments/**/corpus/`,
`eval_results.json`, `ground-truth.json` and any `*.json` a report links to;
`graphify-out/`; `.pi/hindsight*`; `.ua/`.

Never copy `.env`. Do not copy regenerable caches: `.venv`, `.coverage`,
`__pycache__`, `.ruff_cache`, `.pytest_cache`, `output/.pdfi_models`.

Procedure at every removal:

1. Copy with `rsync -a`, source first, destination second.
2. Verify before removing: same file count, same total bytes, and one sha256
   spot check per directory. Show the operator the check output.
3. Only then `git worktree remove <path>`.
4. Record here what moved where, and on what date.

This worktree holds the largest and most valuable set: 40 PDFs, 1,123 page
images, 1,614 transcriptions (about $5.30 of OpenRouter spend), the Stage A
extractions and the local OCR results. It cannot be regenerated for free.
Heavy artefacts should go to a GitHub Release before the final removal, per the
`.gitignore` note.

### Movement log

| Date | From | To | What |
| --- | --- | --- | --- |
| | | | |

## Guardrails

1. `labels.json` and the corpus are frozen. Never edit a label. Run
   `uv run python $E/freeze.py --check` before any measurement. Report drift;
   do not patch digests without telling the operator.
2. Thresholds `0.5` and `0.10` do not change in Experiment 33. Recalibration
   needs its own proposal.
3. Stage B with PaddleOCR-VL (tasks 6.1 to 6.6) stays **unauthorised**. It
   needs a separate operator decision naming the document subset, timeout and
   runtime budget.
4. Keep `pdf_inspector` → `liteparse` → `pypdf` (ADR-066) as the reader chain.
   The poppler and pypdf text layers exist only as the experiment's answer key.
5. OpenRouter is used only for labelling, and labelling is finished.
6. Experiment PDFs, page images, transcripts and extractions are gitignored.
   Keep it that way.

## Known trap

`pdf_inspector.extract_pages_markdown` numbers pages from **0**;
`process_pdf_with_ocr` numbers them from **1**, and so do the labels.
`compare_readers.py` normalises to 1-based. Task 6.7 was unaffected (verified
against `mx02` pages 15 to 17) and PR #95 only counts those lists.
