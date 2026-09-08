# Experiment 24 — OCR routing evaluation (task 5.1)

**ID**: `24-ocr-routing-eval-2026-09-08`
**Date planned**: 2026-09-08
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED (validity gates frozen 2026-09-08, task 1.6)
**Relation**: `improve-rag-input-quality-5` task 5.1; ADR-062 (Proposed); experiment 23 routing gate

## Why this experiment exists

The merged OCR routing (task 2 waves) sends OCR-required PDFs to the
isolated PaddleOCR-VL worker instead of degrading on the fast path. The
routing gate (0.5/0.5) was calibrated on the calibration fixtures only
(experiment 23, task 1.7). This experiment measures the routed candidate
on the five held-out evaluation fixtures against the pinned fast-path
baseline, before any default changes (ADR-062 stays Proposed until then).

## Hypothesis

> Routing OCR-required evaluation PDFs through the isolated worker
> yields structured Markdown with zero structured missing-content
> failures, leaves fast-path outputs byte-identical, keeps worker time
> within 180 s/page at per-page p95, and keeps the routing decision
> within 50 ms at p95.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | routing path | `fast_path_baseline` vs `routed_worker_candidate` |
| Dependent | missing-content failures, structure markers, latency | gates below |
| Dependent | reading order, table fidelity | recorded per task 5.1 |
| Controlled | fixtures | 5 held-out evaluation PDFs (manifest-pinned) |
| Controlled | routing gate | 0.5/0.5 (experiment 23, unchanged) |
| Controlled | worker identity | fingerprint asserted by capability probe |

Not changed: retrieval stack, embedding model, chunker, qrels.

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | `tests/fixtures/pdf_baseline/evaluation/` (task 1.1, licence-safe, self-authored) |
| Files | 5 PDFs: clean text, two-column, scanned, image, mixed |
| Ground truth | pinned pdf-inspector observations + byte-exact fast-path Markdown hashes (`tests/unit/test_pdf_baseline_fixtures.py`) |
| Symlinks | none |

## Metrics

### Primary (gated)

- Structured missing-content failures per cell (target: 0)
- Structure markers per routed fixture (heading/list/table; target ≥ 1)
- Altered fast-path outputs (target: 0)
- Worker seconds/page at p95; routing decision ms at p95

### Diagnostic (recorded, not gated)

- Reading-order fidelity, table/structure fidelity per fixture
- Downstream evidence retrieval on extracted Markdown (task 5.1 scope)
- Per-fixture latency distribution

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json).

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality | 0 structured missing-content failures; every routed fixture ≥ 1 marker | Fast-path failure count pinned at 0 by the baseline unit test |
| Regression | Fast-path fixtures byte-identical — 0 altered | Pinned hashes; routing must not touch clean PDFs |
| Latency | Worker ≤ 180 s/page p95; routing decision p95 ≤ 50 ms | Smoke evidence 33.7–150.8 s/page CPU; measured routing p95 2.26 ms (`output/routing_overhead.json`) |

## Evidence used for the freeze

| Source | What it pins |
| --- | --- |
| `tests/fixtures/pdf_baseline/manifest.json` | pdf-inspector observations, 8 fixtures (2026-09-06) |
| `tests/unit/test_pdf_baseline_fixtures.py` | byte-exact fast-path Markdown |
| `ocr-worker/SMOKE_RESULTS.md` | worker timing, Python 3.11–3.13 |
| `output/routing_overhead.json` | routing decision latency (this experiment, baseline-only) |
| experiment 23 matrix | routing gate 0.5/0.5 |

## Interpretation rules

- All gates pass → ADR-062 evidence complete; promotion decision per task 5.5.
- Quality gate fails → worker output unusable on held-out content; keep `OCR_FALLBACK_ENABLED=false` packaged default; record negative result.
- Regression gate fails → routing bug, not a worker-quality question; fix before any re-run.
- Latency gate fails → investigate per-page cost (page count, cold weights); do not relax the gate.

## Procedure

```bash
# 1. Provision worker (venv from lockfile; weights from preserved cache)
cd ocr-worker && uv sync --locked
export PADDLE_PDX_CACHE_HOME=~/Development/DATA/omrg/ocr-worker/model-cache
export PADDLE_OCR_BASE_DIR=~/Development/DATA/omrg/ocr-worker/model-cache

# 2. Baseline-only routing overhead (already recorded, rerunnable)
uv run python experiments/24-ocr-routing-eval-2026-09-08/measure_routing_overhead.py

# 3. Ablation runner (to be written; declare full cell matrix first)
uv run python experiments/24-ocr-routing-eval-2026-09-08/run_ablation.py --resume
```

## Cleanup

Evaluation fixtures are committed and permanent. Worker venv and model
cache are gitignored and reproducible (see `ocr-worker/DATA_LOCATIONS.md`).
Raw JSON results are committed; nothing large is generated locally.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` | this plan | ✅ |
| `plan.json` | machine-readable gates | ✅ |
| `measure_routing_overhead.py` + `output/routing_overhead.json` | routing baseline | ✅ |
| `run_ablation.py` | ablation runner | to write |
| `results.md` + `output/*.json` | outcomes | ✅ |
