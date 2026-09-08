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

## Reproduction

```bash
cd ocr-worker && uv sync --locked   # venv from lockfile
ln -sfn ~/Development/DATA/omrg/ocr-worker/model-cache .model-cache
cd ..
uv run python experiments/24-ocr-routing-eval-2026-09-08/run_ablation.py --resume
uv run python experiments/24-ocr-routing-eval-2026-09-08/summarise_eval.py
```

## Artefacts

| File | Description |
| --- | --- |
| `plan.json` / `protocol.md` | frozen gates and plan |
| `run_ablation.py` | ablation runner (checkpoint/resume) |
| `measure_routing_overhead.py` | routing-decision latency baseline |
| `output/ablation.json` | per-fixture rows, both cells |
| `output/eval_results.summary.json` | gate checks, machine-readable |