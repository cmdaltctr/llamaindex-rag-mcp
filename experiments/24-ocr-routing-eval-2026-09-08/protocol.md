# Experiment 24 — OCR routing evaluation (task 5.1) — gates frozen

- **Status:** PLANNED (gates frozen 2026-09-08, task 1.6)
- **Date frozen:** 2026-09-08
- **Operator:** Dr Muhammad Aizat Bin Md Hawari with AI agent
- **OpenSpec stage:** Stage 5 candidate evaluation. Gates below were derived
  from Stage 1 baselines and committed BEFORE any candidate measurement.

## Purpose

Compare the current fast-path `pdf-inspector` pipeline with the routed
isolated-worker candidate (ADR-062) on the five held-out evaluation
fixtures, using the routing gate calibrated in task 1.7 (experiment 23:
`OCR_FALLBACK_MIN_CONFIDENCE=0.5`, `OCR_FALLBACK_PAGE_FRACTION=0.5`).

Record reading order, table/structure fidelity, missing content,
failure rate, latency, and downstream evidence retrieval.

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json). Thresholds derive
from pinned baselines, not preference.

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality | 0 structured missing-content failures; every routed fixture emits ≥ 1 heading/list/table marker | Fast-path failure count pinned at 0 by `tests/unit/test_pdf_baseline_fixtures.py` |
| Regression | Fast-path (text_based) fixtures byte-identical to pinned hashes — 0 altered | Same pinned test; routing must not touch clean PDFs |
| Latency | Worker ≤ 180 s/page at per-page p95; routing decision p95 ≤ 50 ms | Smoke evidence tops at 150.8 s/page CPU (`ocr-worker/SMOKE_RESULTS.md`); measured routing p95 2.26 ms (`output/routing_overhead.json`) |

## Evidence used for the freeze

| Source | What it pins |
| --- | --- |
| `tests/fixtures/pdf_baseline/manifest.json` | pdf-inspector observations for all 8 fixtures (2026-09-06) |
| `tests/unit/test_pdf_baseline_fixtures.py` | Byte-exact fast-path Markdown hashes |
| `ocr-worker/SMOKE_RESULTS.md` | Worker parse timing 33.7–150.8 s/page CPU, Python 3.11–3.13 |
| `output/routing_overhead.json` | Routing decision latency, 20 reps × 8 fixtures |
| Experiment 23 calibration matrix | Routing gate 0.5/0.5 (40 zero-error grid cells) |

## Baseline-only measurements already performed

`measure_routing_overhead.py` (this directory) times the routing decision
on every fixture. No candidate path ran before this freeze.

## Next steps

1. Provision the worker venv from `ocr-worker/uv.lock` and point
   `PADDLE_PDX_CACHE_HOME`/`PADDLE_OCR_BASE_DIR` at the preserved cache
   (see `ocr-worker/DATA_LOCATIONS.md`).
2. Write the ablation runner per task 5.1; declare its full cell matrix
   here before running.
3. Run cells; evaluate against the frozen gates only.
