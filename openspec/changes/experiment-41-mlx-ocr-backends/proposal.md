# Experiment 41: MLX OCR Backends

## Why

Experiment 37 accepted dots.mocr as the primary OCR engine and left two costs open. PaddleOCR-VL on CPU timed out on 34 of 257 pages (finding F4). dots.mocr peaked at 22.2 GiB on PyTorch MPS (finding F5). A two-page scratch test on 2026-10-05 ran PaddleOCR-VL on Apple's MLX framework about 13 times faster than on CPU. Two pages of one paper cannot support a decision.

OMRG needs a measured answer on the same 257 pages: can an MLX backend replace the current backend for each engine without losing output quality?

## What Changes

- Add Experiment 41 under `experiments/41-mlx-ocr-backends-<date>/` with a protocol, a plan and, after operator approval, runs.
- Compare four arms on the Experiment 37 page lists (E-maths 40, E-scan 28, E-script 189): dots.mocr on PyTorch MPS (reuse), dots.mocr on MLX bf16 (new), PaddleOCR-VL on CPU (reuse), PaddleOCR-VL on MLX bf16 (new).
- Measure seconds per page, peak memory (client and server processes), timeouts, KaTeX errors, script recall, invented text (operator review) and token similarity to the baseline arm.
- Run each MLX arm alone, with no other GPU job, so timings are clean.
- Record the operator's gates in `plan.json` before any run. The proposal gives candidates only.
- Hold four approvals in `plan.json`, all `false`: install `mlx-vlm`, download model weights, licence check of the MLX conversions, and the OCR run budget.
- Report the two limits of the Experiment 37 baseline (shared load; converted weights) and offer a baseline re-timing control.
- Change no engine folder, route, default or dependency.

## Capabilities

### New Capabilities

- `mlx-ocr-evaluation`: defines the evaluation contract for comparing an MLX backend with the shipped backend of an OCR engine.

### Modified Capabilities

- None.

## Impact

- Adds experiment artefacts only. The MLX environment is gitignored and stays inside the experiment folder.
- No change to `ocr-workers/`, `src/omrg/`, settings or the base install. PyTorch and MLX stay out of the OMRG environment.
- A pass leads to a separate OpenSpec change for an MLX engine folder. A fail leaves both engines on their current backends.
- Model downloads (about 1.8 GB and about 6 GB) and the licence check need the operator's approval first.
