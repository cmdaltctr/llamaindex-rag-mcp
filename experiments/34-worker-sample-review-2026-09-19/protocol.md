# Experiment 34: Worker Sample Review on Real Documents

**ID**: `34-worker-sample-review-2026-09-19`
**Date planned**: 2026-09-19
**Operator**: Dr Muhammad Aizat Bin Md Hawari, with pi coding agent
**Status**: PLANNED — timing revalidation running before the measured pass (see Implementation notes)
**Relation**: OpenSpec change `experiment-34-worker-sample-review` (this branch); PR #96 (`feat/page-level-ocr-routing`, the protocol 1.1 worker code under test); deferred task 2.3 of `page-level-ocr-routing`; Experiment 33 task 6.7 (local tier evidence)

## Why this experiment exists

The PaddleOCR-VL worker has never been measured on this corpus. Every quality statement about it is inference from its design (a vision-language layout model), not measurement: Experiment 33's Stage B was deferred, and the smoke test ran only calibration fixtures.

Three named issues wait on this evidence: the old-book blind spot (`io06`, where local OCR reads at median recall 0.609 while reporting 0.922 confidence), triple-column pages with images (`io04`, the operator's "needs llm maybe" note), and two-column/table structure preservation (`bd01` p4, `bd02` p1, `tl03` p5). The verdicts decide whether the deferred task 2.3 signal experiment proceeds and what it should measure.

## Hypothesis / research question

1. The worker's Markdown preserves column order, heading structure and table shape on the problem pages better than the local tier did (Experiment 33 task 6.7 baselines).
2. On the clean control document the worker introduces no visible regressions (no lost text, no invented structure).
3. The operator judges the output ready for an LLM to use on most problem pages — the "lumped into one paragraph" concern is about presentation, and this measures whether the worker avoids it.

## Background and prior evidence

- Local tier on `needs_ocr` pages: Experiment 33 task 6.7 (`output/local_ocr/summary.json`) — modern print 0.977 median recall; `io06` 0.609 at 0.922 confidence; escalation table.
- Worker smoke evidence (`ocr-worker/SMOKE_RESULTS.md`): parse 34–106 s per page warm, ~290 s initial request with model load, calibration fixtures only.
- Two-column reading order on the LiteParse path: fixed and measured 0.5309 → 0.9613 (PR #96).
- Caveat: the worker's page-listed request path (`predict(page_num=...)`, `pages_markdown` double assembly) has never run against real Paddle until this experiment.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Engine under review | PaddleOCR-VL worker (paddleocr 3.7.0, model PaddleOCR-VL 1.6, CPU), fixed |
| Dependent | Operator checklist verdicts | text accuracy, column order, headings, table, ready-for-LLM, note — per page |
| Dependent (diagnostic) | Per-page seconds, error classes | from `worker_state.json` |
| Controlled | Sample | frozen `sample.json`, 42 pages, seed 34 |
| Controlled | Request shape | one protocol 1.1 page-listed request per document |
| Controlled | Corpus | Experiment 33 frozen corpus, read-only |

Not changed: the worker code (it ships on the base branch), the local tier, routing, any OMRG retrieval setting. This is a measurement of one engine, not an A/B.

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | Experiment 33 frozen corpus (`corpus/natural/*.pdf`), page images `output/.pages/` |
| Local path | Read by absolute path from the Experiment 33 worktree; sample manifest committed here (`sample.json`) |
| Size | 42 pages across 6 documents (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, `bd03` control 6) |
| Ground truth | The operator's eyes against the original page image. Reference transcriptions exist but are NOT scored in this experiment |
| Symlinks | None |

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Worker venv | `ocr-worker/.venv` (provisioned 2026-09-19: paddleocr 3.7.0, paddlepaddle 3.3.1, paddlex 3.7.2) |
| Model cache | `ocr-worker/.model-cache/official_models/PaddleOCR-VL-1.6` (1.9 GB) |
| Protocol | 1.1 (page-listed requests; base branch code) |
| Hardware | Operator's Mac, CPU only |
| Sanity checks | `ocr-worker/.venv/bin/python -m omrg_ocr_worker --capabilities` reports protocol 1.1 |

## Experimental design / cell matrix

| Run ID | Purpose | Content | Expected interpretation |
| --- | --- | --- | --- |
| `timing` | Revalidate per-page cost on this machine | `time_worker.py` — cold + warm page-listed requests | Sets or revises the wall-clock budget before the measured pass |
| `review` | The measured pass | `run_worker.py` over all 42 pages, then `make_review.py` | Operator verdicts per page |

Stop rules: 900 s request timeout per document; wall-clock cap per the approved budget (2 h — under revision from the timing pass); checkpoint per document, resume without re-running.

## Metrics

### Primary metrics

- Operator verdicts per page: accuracy (all/most/some/mostly wrong), columns (correct/wrong/n/a), headings (preserved/lost/n/a), table (readable/broken/n/a), ready-for-LLM (yes/no), note.

### Diagnostic metrics

- Per-page and per-document seconds (steady state vs model load).
- Error classes from the worker (any `parse_error` envelopes).

## Procedure / reproduction commands

```bash
# 1. Freeze the sample (already run; sample.json committed)
python3 experiments/34-worker-sample-review-2026-09-19/freeze_sample.py --exp33 <exp33-dir>

# 2. Timing revalidation (background-safe)
python3 experiments/34-worker-sample-review-2026-09-19/time_worker.py

# 3. Measured pass (checkpointed, resumable)
uv run python experiments/34-worker-sample-review-2026-09-19/run_worker.py

# 4. Build the review page, then open output/review.html and fill the checklist
python3 experiments/34-worker-sample-review-2026-09-19/make_review.py
```

## Success criteria / pass gates

| Criterion | Threshold | Why it matters |
| --- | --- | --- |
| Review completeness | every sampled page has a verdict | an unreviewed page is missing data, not a pass |
| Timing gate | steady-state per-page cost measured before the full pass | the 2 h budget was set from smoke-fixture numbers; real pages may not fit |
| Verdict quality bar (decision input, not a gate) | `io06` and `io04`: what share of pages reach "most correct" + "ready for an LLM" | decides the task 2.3 go/no-go and the worker's standing |
| Control guard | `bd03` shows no "mostly wrong" or "lost/garbled" verdicts | a worker that damages clean pages fails the review regardless of the problem docs |

## Interpretation rules

- Old books readable (`io06` mostly "most correct" + structure preserved): task 2.3's signal experiment proceeds, aimed at routing `io06`-class pages to the worker.
- Old books readable but routing is the gap: 2.3 focuses purely on the confident-but-wrong detection signal.
- Triple column fixed (`io04` columns "correct"): the "needs llm maybe" note is answered by the worker tier; no further engine work needed for that class.
- Control regressions: stop; the worker damages clean pages and must not be trusted for the flip question.
- Worker errors on page-listed requests: the protocol 1.1 Paddle-side path is broken in practice; record, fall back to whole-document requests for the affected documents, and file the finding against the smoke gate.

## What to do if the experiment fails

1. Worker unusable on this hardware within any sane budget: document the negative result, keep `document` mode and the local tier as they are; the task 2.3 decision moves to a machine that can run the worker.
2. Mixed verdicts: record per-document outcomes; 2.3 proceeds scoped only to the document classes that failed.
3. Escalation: an OpenSpec change for any code follow-up (routing signal, worker fix) — never a silent code change born from an experiment.

## Implementation notes

- Code path under test: `ocr-worker/src/omrg_ocr_worker/worker.py` parse seam, protocol 1.1 `pages` / `pages_markdown` path — first contact with real Paddle.
- The measured pass runs one persistent worker process; model load amortises once.
- Timing observations so far: one cold `bd03` page exceeded 900 s; one cold+warm probe exceeded 3000 s without a response. The smoke-evidence figures (34–106 s/page) came from calibration fixtures on a different run. The timing pass must settle the budget before the measured pass; the 2 h cap in the proposal is provisional until then.
- Page images are copied into `output/pages/` for the review page and stay uncommitted (preserve-class on carry-over); verdicts JSON and worker Markdown outputs are committed.

## Cleanup

No indexes to remove. Keep raw outputs (`output/worker/`, `worker_state.json`), `sample.json`, verdicts and `report.md`. The worker venv and model cache are regenerable and stay uncommitted.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `sample.json` | Frozen 42-page manifest | ✅ |
| `freeze_sample.py` / `run_worker.py` / `make_review.py` / `time_worker.py` | Harness | ✅ |
| `output/worker_state.json` | Checkpointed run state + timings | ✅ |
| `output/worker/<doc>/pNNN.md` | Worker Markdown per page | ✅ |
| `output/review.html` | Side-by-side review surface | ✅ |
| `review_verdicts.json` | Operator verdicts, committed unchanged | ✅ |
| `report.md` | Verdict summary and the 2.3 go/no-go | ✅ |

## References

- Experiment 33: `experiments/33-ocr-routing-natural-positive-2026-09-17/` (corpus, labels, task 6.7)
- `ocr-worker/SMOKE_RESULTS.md` (provisioning and fixture parse evidence)
- PR #96 (worker protocol 1.1 and page-routing implementation)
