# Experiment 34: Worker Sample Review on Real Documents

**ID**: `34-worker-sample-review-2026-09-19`
**Date planned**: 2026-09-19
**Operator**: Dr Muhammad Aizat Bin Md Hawari, with pi coding agent
**Status**: RUNNING — review scoped to 4 pages (see Amendments A1); dots.mocr probe added (A2)
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
| Dependent | Operator checklist verdicts | per page and per engine, selectable only (see Metrics) |
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
| Size | Frozen sample: 42 pages across 6 documents (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, `bd03` control 6). **Reviewed set: 4 pages** — `bd03` p1, p2 (control) and `io06` p28, p53 (A1) |
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

- Operator verdicts per page **and per engine** (pdf-inspector, LiteParse, OCR worker), all selectable, no free text (review page v2, operator request 2026-09-24):
  - output produced (text / empty / only noise) — when not "text", the rest is skipped;
  - text accuracy (all / most / some correct / mostly wrong);
  - reading order (correct / minor jumps / scrambled / n/a);
  - headings and structure (preserved / partly / lost or garbled / n/a);
  - tables (readable / text kept, grid lost / missing or broken / n/a);
  - problems seen, multiple choice (none, missing text, invented text, repeated text, wrong characters, broken words, headers/footers mixed in, captions misplaced, image or markup noise);
  - ready for an LLM (yes / after light cleanup / no).
- Per page: the layout of the original PDF page, multiple choice (single, two, three+ columns, tables, figures, old typography, near-blank), and the best engines, multiple choice (pdf-inspector, LiteParse, worker; or none usable, which excludes the others).

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
| Review completeness | every page in the reviewed set (A1) has a verdict | an unreviewed page is missing data, not a pass |
| Timing gate | steady-state per-page cost measured before the full pass | the 2 h budget was set from smoke-fixture numbers; real pages may not fit |
| Verdict quality bar (decision input, not a gate) | `io06` and `io04`: what share of pages reach "most correct" + "ready for an LLM" | decides the task 2.3 go/no-go and the worker's standing |
| Control guard | `bd03` worker verdicts show no "mostly wrong" or "lost or garbled" | a worker that damages clean pages fails the review regardless of the problem docs |

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

## Amendments

### A1 — Review scoped to 4 pages (operator decision 2026-09-19, recorded 2026-09-24)

- Decision: no multi-day run. The operator reviews 4 pages: `bd03` p1, p2 (clean control, two-column) and `io06` p28, p53 (old book; p53 was marked unrecoverable).
- Implemented in commit `46147e1` (`--only` on the runner and the review generator); `output/review_small.html` is the review surface. This protocol was not updated at the time; this entry closes that gap.
- The worker later also ran `bd01`, `bd02`, `io04` and `tl03` at their full sample page lists. Those outputs are kept as diagnostic evidence (timing, error classes), not as reviewed verdicts.
- Consequence for interpretation: 2 control pages and 2 old-book pages cannot settle the `io04` triple-column or `tl03` table questions. The report states per-issue coverage explicitly.

### A2 — dots.mocr probe (operator request 2026-09-24)

- Question: is dots.mocr (rednote-hilab, 3.04 B parameters, MIT plus a supplementary model agreement) usable on this machine, and how does its output compare on the reviewed set?
- Claimed advantage (self-reported, olmOCR-bench): 83.9 overall against 80.0 for PaddleOCR-VL; old scans 48.2 against 37.8; multi-column 85.3 against 79.9; tables 90.7 against 84.1. The model is about 3× larger than PaddleOCR-VL (0.9 B), not smaller.
- Runner: `probe_dots_mocr.py`, a PEP 723 script in its own `uv` environment (PyTorch, transformers 4.57.6). PyTorch never enters the omrg install; the operator approved it for this probe only.
- Apple Silicon patches (upstream targets CUDA): the top-level `flash_attn` import is made optional, and the vision tower uses PyTorch SDPA attention. `PYTORCH_ENABLE_MPS_FALLBACK=1` is set. Weights live in `~/.cache/omrg-exp34/DotsMOCR` (uncommitted, regenerable).
- Input: pages rendered from the source PDFs at 200 DPI (upstream default), raised so the long side is at least 1600 px. At plain 200 DPI the `io06` page box gives 384 × 624 px, far below the embedded scan (983 × 1600); the low-resolution run is kept in `output/dots_mocr_lowres/` as evidence. Prompt: upstream `prompt_layout_all_en`, converted to Markdown with page headers and footers kept. `max_new_tokens` 8192, greedy decoding.
- Pages: the 4 reviewed pages (A1), not the `io04` page first suggested, so that the fourth review column is complete for the reviewed set.
- Outputs: `output/dots_mocr/<doc>/pNNN.md` (+ `.raw.txt`), `output/dots_mocr_state.json` (load and per-page seconds, tokens, token-cap hits, parse success, MPS memory).
- Review: the probe appears as a fourth engine panel with the same checklist; "best output" gains a dots.mocr option. The probe engine is optional: pages it did not run do not block review completeness.
- Result (2026-09-24, `output/dots_mocr_state.json`): all 4 pages completed with no error, no token-cap hit and valid layout JSON. Model load 3.4 s; per page 49.8 s (`bd03` p1), 38.2 s (p2), 16.8 s (`io06` p28), 6.7 s (p53); MPS memory about 7–9 GB. For comparison, the PaddleOCR-VL worker took 334.5 s for `bd03` p1–p2 and 85.2 s for `io06` p28 + p53. Weights download: 698 s after the Hugging Face Xet transfer stalled and was disabled (`HF_HUB_DISABLE_XET=1`).
- Resolution matters: at 384 px `io06` p28 kept the printed line breaks and hyphenation and misread words (`ausu`, `Ciuiili`, `forores`); at 1600 px it joined lines and repaired them (`auus`, `Ciuili`, `sorores`). On near-blank `io06` p53 it emits bleed-through noise (`io u- n- L c; …`) plus page numbers at both resolutions — where the worker returned nothing.
- Decision use: an input to whether a later experiment compares dots.mocr against PaddleOCR-VL on the full sample. It does not change this experiment's pass gates.

### A3 — Review checklist v2 (operator request 2026-09-24)

- Per-engine, selectable-only checklist replaces the single free-text checklist (see Metrics). "Best output" is multiple choice. The page-layout question asks about the original PDF page. The rendered view shows `**bold**` and `*italic*` so emphasis marking is visible per engine; literal HTML tags stay visible as text.

### A4 — Maths rendering and a display-equation page (operator request 2026-09-24)

- Trigger: on `bd03` p2 the dots.mocr panel looked as if formulas were not extracted. The cause was the review page, not the model. dots.mocr writes chemical formulas as inline LaTeX (`$\text{SiO}_2$`), and the review page showed LaTeX as plain text. The other engines use Unicode subscripts (`SiO₂`).
- Review page: `make_review.py` loads KaTeX 0.16.22 (auto-render, from cdn.jsdelivr.net). It renders `$…$` and `$$…$$` in the rendered view; the raw view stays as source. The page needs network access for this; offline, the LaTeX source shows.
- No page in the reviewed set has display equations. To test the formula claim in the dots.mocr demo, the probe ran on one page outside the frozen sample: `eq01` p11 = Kingma & Welling, "Auto-Encoding Variational Bayes", arXiv 1312.6114v11, appendix B–D. The PDF goes in `corpus/eq01.pdf` (gitignored); the probe writes the page image.
- `eq01` p11 appears only in `review_small.html` (`--only`), with dots.mocr as its only engine. `review.html` keeps the 42-page frozen sample. The page does not count towards any pass gate.
- Result: 55.7 s, 1,937 tokens, valid JSON. All 4 display blocks came back as correct LaTeX `align`/`align*` environments, with equation tags (11) and (12), bold vectors and `\mathcal{N}`. All 59 formulas on `eq01` p11 and `bd03` p1–p2 (dots.mocr and worker) render in KaTeX with no error.
- Probe fixes found on the way: (1) the model adds its own `$$` around formulas, so the converter now strips them before wrapping (the earlier `.md` files did not change; `eq01` was rebuilt from `.raw.txt`). (2) The `flash_attn` patch was not idempotent: the patched copy still contained the import as a substring, so a second run wrapped it again and broke the file. The test now matches only at line start.

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
| `output/review.html`, `output/review_small.html` | Review surfaces (full sample; reviewed set) | ✅ |
| `probe_dots_mocr.py`, `output/dots_mocr/`, `output/dots_mocr_state.json`, `output/pages/eq01/` | dots.mocr probe (A2, A4) | ✅ |
| `review_verdicts.json` | Operator verdicts, committed unchanged | ✅ |
| `report.md` | Verdict summary and the 2.3 go/no-go | ✅ |

## References

- Experiment 33: `experiments/33-ocr-routing-natural-positive-2026-09-17/` (corpus, labels, task 6.7)
- `ocr-worker/SMOKE_RESULTS.md` (provisioning and fixture parse evidence)
- PR #96 (worker protocol 1.1 and page-routing implementation)
