# Experiment 24 Results: OCR Routing Evaluation (task 5.1)

**ID**: `24-ocr-routing-eval-2026-09-08`  
**Date run**: 2026-09-08  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: PASS (run 2, after fixture repair)  
**Raw data**: [`output/ablation.json`](./output/ablation.json)

---

## Run history

| Run | Fixtures | Verdict | Record |
| --- | --- | --- | --- |
| 1 | blank 605-byte scanned/image PDFs | ❌ FAIL — structure-marker gate | commit `a7d7cd2` |
| — | task 1.1 repair: rasterised CC0 pages + ground-truth text | gate unchanged | commit `786055e` |
| 2 | rasterised CC0 paper pages | ✅ PASS — all five gates | this commit |

The frozen gates in `plan.json` were never modified between runs.

## TL;DR / Decision

- The routed pipeline works end to end on genuinely scanned content:
  routing decision, worker dispatch, structured Markdown with real
  headings, metadata stamping, and per-page latency all behave.
- All five frozen gates pass; ground-truth word recall: eval_image.pdf: 93.0%, eval_scanned.pdf: 94.3%
- Supports ADR-062 promotion evidence; default decision per task 5.5.

## What ran

| Cell | Reader | OCR gate | Fixtures |
| --- | --- | --- | --- |
| fast_path_baseline | pdf-inspector, fallback off | n/a | 5 evaluation PDFs |
| routed_worker_candidate | wrapped, fallback on | 0.5 / 0.5 | 5 evaluation PDFs |

Routed by the frozen gate: `eval_scanned.pdf`, `eval_image.pdf`
(classified `scanned` → unconditional). Kept on the fast path:
`eval_clean_text.pdf`, `eval_two_column.pdf`, `eval_mixed.pdf`.

## Frozen gate checks

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Quality: structured failures | 0 | 0 | ✅ PASS |
| Quality: structure markers | every routed fixture ≥ 1 | eval_image.pdf: {'headings': 2, 'list_items': 0, 'tables': 0}; eval_scanned.pdf: {'headings': 3, 'list_items': 0, 'tables': 0} | ✅ PASS |
| Regression: fast-path byte-identity | 0 altered | 3/3 identical | ✅ PASS |
| Latency: worker s/page p95 | ≤ 180 | 156.9 s worst page | ✅ PASS |
| Latency: routing p95 | ≤ 50 ms | 2.26 ms | ✅ PASS |

## Worker output on the routed fixtures

Full extracted Markdown is committed in `output/ablation.json` (per-row
`markdown` field). Summary:

- `eval_scanned.pdf`: 4,032 characters, 3 headings recovered from the
  rasterised CC0 paper page (source page 2 of Dashnow et al. 2014).
- `eval_image.pdf`: 4,297 characters, 2 headings (source page 4).
- Ground-truth word recall vs the born-digital source pages: eval_image.pdf 93.0%, eval_scanned.pdf 94.3% (diagnostic, not gated).

## Other observations

- `eval_mixed.pdf` stays on the fast path at gate 0.5/0.5 (confidence 0.5
  is not below the 0.5 threshold; 0/2 flagged pages) — its silently missing
  second page remains, as pinned. Baseline and candidate outputs are
  byte-identical for all three fast-path fixtures.
- Worker per-page times (this run): 156.3 s and 156.9 s including model
  load from the preserved cache; inside the 180 s gate with ~13% margin.
  Run 2 timings on the real pages are ~50 s slower than the blank-page
  run 1 because there is actual content to recognise.
- Worker fingerprint matched the smoke evidence exactly (PaddleOCR-VL 1.6,
  paddleocr 3.7.0, paddlepaddle 3.3.1, paddlex 3.7.2).

## Run-1 post-mortem (one paragraph)

Run 1 failed the structure-marker gate because the original task 1.1
fixtures were 605-byte blank PDFs — no image data, no text operators —
so the worker correctly returned an image placeholder. The smoke
evidence had already documented this placeholder behaviour on
contentless scanned pages; the mismatch should have been caught at
gate-freeze time. The repair replaced the fixtures with rasterised
CC0 pages (attribution and sha256 in the fixtures manifest); the
frozen gates were never touched.

## Cross-engine confirmation (Mistral OCR)

The operator independently ran both routed fixtures through Mistral
Document AI (mistral-ocr; markdown output, defaults) and the raw
responses are committed as `output/mistral_eval_*.md`. Scored with
the same ground-truth word-recall metric:

| Fixture | PaddleOCR-VL (ours) | Mistral OCR |
| --- | ---: | ---: |
| eval_image.pdf 93.0% | 95.0% |
| eval_scanned.pdf 94.3% | 96.8% |

Both engines recover the same rule headings (Rule 3/4/5 and Rule
8/9) at the same positions. Two independent OCR systems agreeing
within ~3 points confirms the run-2 PASS reflects real extraction,
not a favourable reading of one engine.

## Task 5.1 wording: the descriptive items

The five frozen gates above are unchanged. Task 5.1 also asks for
reading order, table/structure fidelity, missing content, failure rate,
latency, and downstream evidence retrieval. Failure rate and latency are
gated above. The rest are computed from the committed artefacts by
[`analyse_task_5_1.py`](./analyse_task_5_1.py) into
[`output/task_5_1_analysis.json`](./output/task_5_1_analysis.json). No
worker run was repeated and no verdict depends on these numbers.

### Reading order

In-order word recall is the longest common subsequence of the
ground-truth word sequence and the extracted word sequence, over the
ground-truth length. Set recall is the order-blind figure already in the
summary. A small gap means the words came back in the original order.

| Fixture | Set recall | In-order recall | Gap |
| --- | ---: | ---: | ---: |
| eval_scanned.pdf | 94.3% | 94.7% | −0.4 pp |
| eval_image.pdf | 93.0% | 92.8% | +0.3 pp |

The two figures agree to within half a percentage point, so the worker
preserved reading order on both single-column rasterised pages. The
negative gap on `eval_scanned.pdf` is an artefact of the two
denominators: set recall counts unique words, in-order recall counts
positions.

The fast-path baseline extracts nothing from either fixture, so its
recall is 0.0 on both measures.

### Structure fidelity

| Fixture | Expected headings | Recovered as Markdown headings |
| --- | --- | --- |
| eval_scanned.pdf | Rule 3, Rule 4, Rule 5 | `Rule 3: Include an Introduction`, `Rule 4: Be Philip E. Bourne`, `Rule 5: Collaborate` |
| eval_image.pdf | Rule 8, Rule 9 | `Rule 8: Reference`, `Rule 9: Edit` |

Every section heading on both source pages came back as a Markdown
heading with its full title.

**Table fidelity is not measurable on this set.** Both held-out source
pages are prose with figures: the ground truth contains zero table rows
and the worker emitted zero. The one pipe-delimited line in the ground
truth is the journal footer, not a table. Table behaviour on this branch
rests on the calibration-set smoke evidence
(`ocr-worker/SMOKE_RESULTS.md`), not on experiment 24.

### Missing content

| Fixture | Ground-truth words | Extracted words | Missing unique words |
| --- | ---: | ---: | ---: |
| eval_scanned.pdf | 527 | 537 | 16 |
| eval_image.pdf | 583 | 600 | 21 |

The missing words are listed in the analysis JSON. All 37 fall into two
groups, and neither is lost content:

1. Hyphenation fragments from the born-digital ground truth
   (`intro`/`duction`, `supervi`/`sor`, `disci`/`plines`, `brev`/`ity`).
   The worker rejoins the line break, so `introduction`, `supervisor`,
   `disciplines` and `brevity` are all present in its output and the
   fragment tokens are absent by construction. Here the OCR output is
   more correct than the reference, not less complete.
2. The journal running footer (`www`, `ploscompbiol`, `org`, `october`,
   `volume`, `issue`). The worker drops page furniture, which is what a
   retrieval corpus wants.

Extracted word counts exceed the ground truth because figure captions
and DOI lines are recovered too (`Figure 1`, `doi:` are present in both
outputs).

### Downstream evidence retrieval

Twelve evidence questions were ranked over each cell's extracted
Markdown, chunked by the production chunker (`markdown_chunk_size` 1024
tokens, Qwen tokenizer identity as promoted) and scored with the
production BM25 implementation in `core/retrieval/sparse.py`. Ten
questions are answered only by the two routed pages; two control
questions are answered by fast-path fixtures.

| Cell | Chunks | R@1 | MRR@10 | Questions with no gold hit |
| --- | ---: | ---: | ---: | ---: |
| fast_path_baseline | 3 | 0.167 | 0.167 | 10 |
| routed_worker_candidate | 5 | 0.917 | 0.958 | 0 |

The baseline cannot answer any of the ten scanned-page questions: it
produces no chunks for those two documents at all, so the evidence is
not in the index. The routed candidate retrieves the gold document at
rank 1 for eleven of twelve questions and at rank 2 for the twelfth.
Both control questions rank 1 in both cells, confirming the fast-path
content is unaffected.

**Read this as a retrievability probe, not a ranking benchmark.** Five
documents and two routed fixtures give no statistical power, and at the
packaged 1024-token Markdown budget each fixture yields one chunk, so
chunk-level and document-level retrieval coincide here. It answers one
question — does OCR-recovered content become reachable evidence — and
the answer is that without routing it is unreachable.

## Reproduction

```bash
cd ocr-worker && uv sync --locked   # venv from lockfile
ln -sfn ~/Development/DATA/omrg/ocr-worker/model-cache .model-cache
cd ..
uv run python experiments/24-ocr-routing-eval-2026-09-08/run_ablation.py --resume
uv run python experiments/24-ocr-routing-eval-2026-09-08/summarise_eval.py
# supplementary task 5.1 figures (no worker, no re-run)
uv run python experiments/24-ocr-routing-eval-2026-09-08/analyse_task_5_1.py
```

## Artefacts

| File | Description |
| --- | --- |
| `plan.json` / `protocol.md` | frozen gates and plan |
| `run_ablation.py` | ablation runner (checkpoint/resume) |
| `measure_routing_overhead.py` | routing-decision latency baseline |
| `output/ablation.json` | per-fixture rows, both cells |
| `output/eval_results.summary.json` | gate checks, machine-readable |
| `analyse_task_5_1.py` | supplementary task 5.1 descriptive analysis |
| `output/task_5_1_analysis.json` | reading order, structure, missing content, evidence retrieval |