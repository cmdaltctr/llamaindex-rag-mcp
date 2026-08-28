# Experiment 17: Reranker MPS vs ONNX CPU latency

**ID**: `17-reranker-mps-vs-onnx-cpu-2026-08-11`
**Date planned**: 2026-08-11
**Operator**: Dr Muhammad Aizat Md Hawari with AI build agent
**Status**: FAIL (H1-H4 PASS, H5 FAIL)
**Relation**: OpenSpec change `apple-acceleration-for-reranker`; ADR-038 (pluggable
reranker backend); ADR-043 (Apple acceleration verdict); follows Experiment 16
(CoreML evidence for ModernBERT)

---

## Why this experiment exists

ADR-038 made Apple MPS reachable through the optional torch reranker, but the
project has no measured evidence for its value on the default MiniLM model.
Experiment 16 ruled out ONNX CoreML for ModernBERT; it did not measure PyTorch
MPS or the MiniLM model that ships as the production default.

This experiment measures the remaining acceleration route (PyTorch MPS via
Sentence Transformers) and records a hardware-specific verdict in ADR-043.

## Hypothesis / Research question

| Gate | Criterion | Meaning |
| --- | --- | --- |
| H1 | 17C loads, selects MPS, and completes without CPU fallback | MPS is usable |
| H2 | 17C P50 is at least 20% lower than 17B P50 | MPS materially accelerates torch |
| H3 | 17C P50 is at least 20% lower than 17A P50, and 17C P95 does not exceed 17A P95 | MPS improves the project baseline |
| H4 | 17C cold start is at most 3 times 17A, and peak RSS is at most 2 times 17A | Operational cost is bounded |
| H5 | 17B and 17C return identical top-ranked documents; 17A and 17C also match for every query | Device and backend changes preserve the workload outcome |

The 20% threshold represents practical significance for a new runtime path.

## Background and prior evidence

- **ADR-038**: added `SentenceTransformerReranker` behind the `torch` optional
  extra. The production class constructs `sentence_transformers.CrossEncoder`
  without a `device` argument. Sentence Transformers 5 selects the strongest
  available device when `device` is omitted. On a compatible Mac, this can
  select MPS.
- **Experiment 16** (`experiments/16-reranker-coreml-fp16-2026-08-03/`): measured
  ModernBERT CoreML fp16. CoreML is 2.3x slower than int8 CPU (5393 ms vs
  2348 ms P50). CoreML does not accelerate cross-encoder models. That experiment
  used ModernBERT, not MiniLM; its absolute timings cannot serve as the MiniLM
  baseline.
- **Model cache key**: `(backend_name, model_id)`. It has no device axis.
- **ONNX default**: CPU. On Apple ARM, MiniLM prefers
  `onnx/model_qint8_arm64.onnx`.
- **Experiment 16 process contamination**: ONNX Runtime process-level state
  leaks between cells. Fresh child processes also isolate device memory and
  peak RSS. This experiment uses one child process per cell repetition.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Backend + device | 17A: ONNX CPU; 17B: torch CPU; 17C: torch MPS |
| Dependent | Load success (H1) | boolean — MPS available and selected |
| Dependent | Warm P50 latency (H2, H3) | ms over 5 iterations, median of 3 repetitions |
| Dependent | Warm P95 latency (H3) | ms, guard against tail regression |
| Dependent | Cold-start time (H4) | seconds from cached-model construction to ready |
| Dependent | Peak RSS (H4) | MB via `resource.getrusage` |
| Dependent | Ranking consistency (H5) | identical top-ranked doc indices per query |
| Controlled | Model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (all cells) |
| Controlled | Workload | Fixed `workload.json` — 5 queries x 20 docs, varied lengths |
| Controlled | Batch size | 32 (matches production `rerank()`) |
| Controlled | Max length | `TOKENIZER_MAX_LENGTH` capped at model's `max_position_embeddings` |
| Controlled | Warm-up | 1 discarded warm-up iteration per repetition |
| Controlled | Iterations | 5 measured iterations per repetition |
| Controlled | Repetitions | 3 independent repetitions per cell (fresh process each) |

**Not changed:** retrieval quality, threshold scaling, embedding model,
ChromaDB, runtime code, default configuration, model choice. This experiment
does not touch retrieval or production code.

## Corpus and ground truth

No retrieval corpus. The workload is a fixed inference benchmark that stresses
the cross-encoder scoring path.

| Item | Value |
| --- | --- |
| Source | Copied from Experiment 16's `workload.json` |
| Local path | `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/workload.json` |
| Size | 5 queries x 20 candidate docs = 100 query-doc pairs per iteration |
| Length distribution | 7 docs at ~50 tokens, 7 at ~100 tokens, 6 at ~200 tokens |

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| onnxruntime | bundled via `uv sync` |
| torch + sentence-transformers | via `torch` optional extra (`uv sync --extra torch`) |
| pandas + matplotlib | via `torch` extra or manual install |
| Hardware | Apple Silicon Mac (M-series), >= 16 GB RAM |
| Model download | MiniLM ONNX (~23 MB quantised) + torch weights (~90 MB) fetched on first run |

```bash
# Sanity checks before running
uv sync --extra torch
uv run python -c "import torch; print('torch', torch.__version__); print('mps built', torch.backends.mps.is_built()); print('mps available', torch.backends.mps.is_available())"
```

## Experimental design / cell matrix

| Run ID | Purpose | Construction | Device | Expected interpretation |
| --- | --- | --- | --- | --- |
| `17A` | Current project baseline | Production `CrossEncoderReranker` | ONNX CPU | The path every user gets today |
| `17B` | Torch control | Experiment adapter around `CrossEncoder` | `device="cpu"` | Isolates MPS effect from torch effect |
| `17C` | MPS candidate | Experiment adapter around `CrossEncoder` | `device="mps"` | The open question: does MPS help? |

**Untimed preflight**: uses `SentenceTransformerReranker` without a device
override. Records the selected device and verifies the current automatic path.

**Stop rules:**
- If 17C fails to select MPS (H1 FAIL): record MPS as unavailable or
  unsupported. Still complete 17A and 17B. Close as FAIL for H1.
- If 17C selects MPS but an unsupported operation falls back to CPU: the
  runner fails H1 (PYTORCH_ENABLE_MPS_FALLBACK=0 prevents silent fallback).

### Cold-start definition

Cold start measures **cached model construction and session initialisation**.
It excludes network download time. Both model formats are prefetched before
any timed cell.

### Process isolation

A coordinator starts a fresh child process for each cell and repetition. This
limits cache-order effects and produces three independent cold-start and
peak-memory observations. It also isolates ONNX Runtime process-level state
(Experiment 16 finding).

## Metrics

### Primary metrics

- **Load + device success (H1):** did cell 17C load, select MPS, and complete
  without CPU fallback? (gated, boolean)
- **Warm P50 latency (H2, H3):** median ms per `rerank()`-equivalent call
  across 5 iterations, then median of 3 repetition-level P50s (gated)
- **Warm P95 latency (H3):** 95th percentile ms (guard against tail regression)
- **Cold-start time (H4):** seconds from cached construction to ready
- **Peak RSS (H4):** MB via `resource.getrusage`
- **Ranking consistency (H5):** identical top-ranked doc indices per query

### Diagnostic metrics

- MPS current allocated memory (17C only)
- MPS driver allocated memory (17C only)
- Mean, min, max latency
- Per-iteration latency series
- Full ranking correlation and score differences across cells
- Resolved ONNX variant (17A)
- Requested vs selected device (17B, 17C)
- torch, sentence-transformers, onnxruntime, tokenizers versions
- macOS version, chip, memory

## Procedure / reproduction commands

### Step 1: Verify environment

```bash
uv sync --extra torch
uv run python -c "import torch; print('mps', torch.backends.mps.is_built(), torch.backends.mps.is_available())"
```

### Step 2: Run the benchmark

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/run_eval.py \
  --repetitions 3 \
  --iterations 5 \
  --resume \
  2>&1 | tee experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/output/run_eval.log
```

The runner prefetches both model formats on first run, then spawns a fresh
child process for each cell repetition. It saves per-repetition results to
`output/checkpoint/` and a merged `eval_results.json`.

### Step 3: Summarise

```bash
uv run python experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/summarise_eval.py
```

Writes `results.md` from the JSON data.

### Step 4: Analysis (optional)

```bash
uv run python experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/analysis.py
```

## Success criteria / pass gates

Written before running. Gates use the median of the three repetition-level values.

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| H1 — MPS usable | 17C loads, selects MPS, no fallback | If MPS is unavailable, nothing else matters |
| H2 — MPS accelerates torch | `17C_P50 <= 0.8 * 17B_P50` | MPS must materially beat torch CPU |
| H3 — MPS beats ONNX CPU | `17C_P50 <= 0.8 * 17A_P50` AND `17C_P95 <= 17A_P95` | MPS must improve the production baseline |
| H4 — Operational cost bounded | `17C_cold <= 3 * 17A_cold` AND `17C_RSS <= 2 * 17A_RSS` | Cold start and memory must stay sane |
| H5 — Ranking consistency | 17B==17C rankings AND 17A==17C rankings (all queries) | Backend/device change must preserve outputs |

## Interpretation rules

- **H1 FAIL:** record MPS as unavailable or unsupported on the tested stack.
  Keep ONNX CPU as the default. Close as FAIL.
- **H1, H2 PASS; H3 FAIL:** MPS accelerates torch but ONNX CPU remains
  preferable. Keep ONNX CPU. Close as INCONCLUSIVE for adoption.
- **H1 to H4 Pass; H5 FAIL:** reject adoption because results change on the
  fixed workload. Keep ONNX CPU. Close as FAIL for adoption.
- **H1 to H5 Pass:** propose a separate OpenSpec change for explicit device
  configuration, backend policy, and device-aware cache keys. Close as PASS.
- **Any negative result:** keep ONNX CPU as the default.

## What to do if the experiment fails

1. **MPS unavailable (H1):** document the exact environment. Keep ONNX CPU.
   Close as FAIL. No follow-up unless hardware or torch changes.
2. **MPS slower than CPU (H2 FAIL):** MiniLM is too small for GPU dispatch
   costs. Record as a model-specific decision. Keep ONNX CPU.
3. **Ranking mismatch (H5 FAIL):** investigate numerical precision differences.
   Keep ONNX CPU. Record the mismatch as a backend-divergence finding.
4. **Escalation:** if H1 to H5 all pass, open a follow-up OpenSpec change for
   `auto|cpu|mps` device configuration with device-aware cache keys.

## Implementation notes

- **17A code path:** production `CrossEncoderReranker.rerank()` via
  `rag_mcp.core.retrieval.reranker`. Batch size 32, sigmoid normalisation,
  `tokenizers` package (not `transformers`).
- **17B/17C code path:** experiment adapter around
  `sentence_transformers.CrossEncoder` with explicit `device` parameter.
  Matches production scoring: identity activation, sigmoid once, batch size 32,
  same effective max length.
- **MPS fallback:** `PYTORCH_ENABLE_MPS_FALLBACK=0` set before torch import in
  child processes. If MPS encounters an unsupported op, the run fails rather
  than silently falling back to CPU.
- **MPS synchronisation:** `torch.mps.synchronize()` called immediately before
  and after every timed MPS inference to prevent asynchronous execution from
  under-reporting latency.
- **Scope boundary:** latency and device selection only. No retrieval quality.
  No runtime code changes.

## Cleanup

```bash
# Model files are cached by huggingface_hub in ~/.cache/huggingface — leave
# them; they are reused by production. No ChromaDB indexes are created.
# Only remove the run log and checkpoint if desired:
rm -rf experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/output/
```

Keep raw JSON and `results.md`.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | Yes |
| `workload.json` | Fixed query-doc workload (5 x 20 pairs, varied lengths) | Yes |
| `run_eval.py` | Coordinator + child runner — 3 cells x 3 repetitions | Yes |
| `test_gates.py` | Focused tests for gate calculations, device assertions, repetition keys, checkpoint resume | Yes |
| `summarise_eval.py` | Aggregates JSON into `results.md` | Yes |
| `analysis.py` | Jupytext percent format — loads JSON, plots latency and memory | Yes |
| `results.md` | Human-readable result report | Yes |
| `output/eval_results.json` | Raw per-cell, per-repetition data | Yes |
| `output/eval_results.summary.json` | Gate evaluation summary | Yes |
| `output/checkpoint/` | Per-repetition checkpoint files | Yes |
| `output/run_eval.log` | Run log | Optional |

## References

- `src/rag_mcp/core/retrieval/reranker.py` — ONNX backend (17A code path)
- `src/rag_mcp/core/retrieval/reranker_torch.py` — torch backend (preflight code path)
- ADR-038 — pluggable reranker backend
- ADR-043 — Apple acceleration verdict (this experiment's result)
- Experiment 16 — `experiments/16-reranker-coreml-fp16-2026-08-03/`
- PyTorch MPS docs: https://pytorch.org/docs/stable/notes/mps.html
