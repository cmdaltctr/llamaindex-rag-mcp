# Experiment 16: Reranker CoreML EP + fp16 feasibility and latency

**ID**: `16-reranker-coreml-fp16-2026-08-03`
**Date planned**: 2026-08-03
**Operator**: Dr Muhammad Aizat Md Hawari with AI build agent
**Status**: PLANNED
**Relation**: OpenSpec change `swap-reranker-to-gte-modernbert` (AIE-20); informs the
provider-default and variant-selection logic in `src/rag_mcp/reranker.py`

---

## Why this experiment exists

The reranker (`src/rag_mcp/reranker.py`) currently runs **CPU-only** by default.
A previous session disabled CoreML EP because it crashed with
`"Error in dynamically resizing for sequence length"` — CoreML cannot handle the
variable sequence lengths that cross-encoder batching produces. The env flag
`RERANK_ONNX_PROVIDER` defaults to `"cpu"` (lines 204–219).

The upcoming swap to `Alibaba-NLP/gte-reranker-modernbert-base` reopens the
question. CoreML EP accelerates **fp16** graphs on the Apple Neural Engine but
does little for **int8** quantised graphs. The swap's default plan picks the
int8 variant (`model_quantized.onnx`, 151 MB) on all platforms. If fp16 +
CoreML loads without the crash and is faster, the swap design should prefer
fp16 on M-series Macs instead.

This experiment answers three things the swap A/B (retrieval quality) does not:
does fp16 load under CoreML, is it faster than int8 on CPU, and what is the
memory footprint. It is a **micro-benchmark** — no corpus, no ground truth, no
retrieval quality. It runs before the swap A/B so the A/B benchmarks the
correct variant as its "gte" cell.

## Hypothesis / Research question

1. **H1 (loadability):** The fp16 variant (`model_fp16.onnx`) loads under
   `CoreMLExecutionProvider` without the dynamic-resize crash that disabled
   CoreML for the legacy MiniLM model.
2. **H2 (speed):** fp16 + CoreML P50 inference latency is lower than int8 + CPU
   P50 latency on the same workload.
3. **H3 (footprint):** fp16 + CoreML cold-start time and peak RSS are not
   pathological (within 3× of int8 + CPU).

## Background and prior evidence

- **Code path under test:** `CrossEncoderReranker._load_model()` and
  `rerank()` in `src/rag_mcp/reranker.py` (lines 130–320). The benchmark
  mirrors the inference loop (batch size 32, sigmoid normalisation) directly
  via `onnxruntime` + `AutoTokenizer` to control the single variable.
- **CoreML disable commit:** `reranker.py` lines 204–219 — CoreML off by
  default, `RERANK_ONNX_PROVIDER=coreml` to re-enable.
- **Swap design:** `openspec/changes/swap-reranker-to-gte-modernbert/design.md`
  Decision 2 — variant fallback chain `model_quantized → model_int8 →
  model_fp16 → model.onnx`.
- **Model:** `Alibaba-NLP/gte-reranker-modernbert-base` ships 8 official ONNX
  variants on HF Hub (uploaded by thenlper, 2025-01). fp16 = 300 MB, int8
  quantised = 151 MB.
- **Known caveat:** CoreML EP's dynamic-shape limitation is an ORT-level
  constraint, not model-specific. It may still crash with fp16. H1 is genuinely
  uncertain — that is why this experiment exists.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | ONNX variant + execution provider | Cell A: int8 + CPU; Cell B: fp16 + CoreML; Cell C: fp16 + CPU |
| Dependent | Load success (H1) | boolean — crash vs clean load |
| Dependent | Warm inference latency (H2) | P50, P95, mean (ms) over N iterations |
| Dependent | Cold-start load time (H3) | seconds from download-complete to session-ready |
| Dependent | Peak RSS (H3) | MB during inference |
| Controlled | Model | `Alibaba-NLP/gte-reranker-modernbert-base` (all cells) |
| Controlled | Workload | Fixed `workload.json` — 10 queries × 20 docs, varied doc lengths |
| Controlled | Batch size | 32 (matches production `rerank()`) |
| Controlled | max_length | 2048 (matches `TOKENIZER_MAX_LENGTH` default) |
| Controlled | Iterations | 20 warm iterations per cell (discard first as JIT warmup) |

**Not changed:** retrieval quality, threshold scaling, embedding model, ChromaDB.
This experiment does not touch retrieval at all.

## Corpus and ground truth

No retrieval corpus. The "ground truth" is a fixed inference workload that
stresses the dynamic-shape code path CoreML struggles with.

| Item | Value |
| --- | --- |
| Source | Synthetic, hand-authored to span short/medium/long doc lengths |
| Local path | `experiments/16-reranker-coreml-fp16-2026-08-03/workload.json` |
| Size | 10 queries × 20 candidate docs = 200 query-doc pairs per cell |
| Length distribution | ~7 docs at ~50 tokens, ~7 at ~200 tokens, ~6 at ~500 tokens (per query) |
| Why varied lengths | Dynamic padding across a batch is exactly what triggers the CoreML resize error — a faithful stress test |

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| onnxruntime | bundled via `uv sync` (CoreML EP included in macOS arm64 wheel) |
| Hardware | Apple Silicon Mac (M-series), ≥ 16 GB RAM |
| Model download | fp16 (300 MB) + int8 (151 MB) fetched on first run via `huggingface_hub` |

```bash
# Sanity checks before running
uv sync
uv run python -c "import onnxruntime as ort; print(ort.get_available_providers())"
# Expect: ['CPUExecutionProvider', 'CoreMLExecutionProvider', ...] on macOS arm64
```

## Experimental design / cell matrix

| Run ID | Purpose | Variant | Provider | Expected interpretation |
| --- | --- | --- | --- | --- |
| `16A` | Baseline — the swap's default plan | `model_quantized.onnx` (int8) | CPU | Production-shaped baseline latency |
| `16B` | Candidate — the question this experiment exists to answer | `model_fp16.onnx` | CoreML EP (fallback CPU) | If it loads and beats 16A on P50, fp16+CoreML becomes the M-series default |
| `16C` | Control — isolates CoreML effect from fp16 effect | `model_fp16.onnx` | CPU | If 16B beats 16A but 16C does not, the win is CoreML. If 16C also beats 16A, the win is fp16 precision, not the EP |

**Stop rules:**
- If 16B crashes on load (H1 FAIL): record the error, skip 16B inference
  measurement, still run 16C. Experiment concludes CoreML is dead for this
  model family — no further CoreML cells.
- If 16B loads but 16C is faster than 16B: CoreML is actively harmful; note it.

## Metrics

### Primary metrics

- **Load success:** did `InferenceSession(providers=[CoreML, CPU])` return
  without exception? (H1 — gated, boolean)
- **Warm P50 latency:** median ms per `rerank()`-equivalent call over 20
  iterations, first iteration discarded (H2 — gated)
- **Warm P95 latency:** 95th percentile ms (H2 — diagnostic)

### Diagnostic metrics

- Cold-start load time (seconds)
- Peak RSS (MB) via `resource.getrusage`
- Mean latency, min, max
- Per-iteration latency series (for jitter analysis)
- Provider actually used (verify CoreML EP took the graph, not silently fell
  back to CPU — check `session.get_providers()`)

## Procedure / reproduction commands

### Step 1: Verify environment

```bash
uv sync
uv run python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

### Step 2: Run the benchmark

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/16-reranker-coreml-fp16-2026-08-03/run_eval.py \
  --iterations 20 \
  2>&1 | tee experiments/16-reranker-coreml-fp16-2026-08-03/output/run_eval.log
```

The runner downloads both variants on first run (~451 MB total), then measures
each cell. It saves `eval_results.json` with per-cell and per-iteration data.

### Step 3: Summarise

```bash
uv run python experiments/16-reranker-coreml-fp16-2026-08-03/summarise_eval.py
```

Writes `results.md` from the JSON data.

## Success criteria / pass gates

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| H1 — fp16 + CoreML loads without crash | clean load, no exception | If it crashes, CoreML stays off; nothing else matters |
| H2 — fp16 + CoreML P50 < int8 + CPU P50 | `16B_P50 < 16A_P50` | CoreML must actually help, not just load |
| H2 — margin is meaningful | `16A_P50 - 16B_P50 >= 5 ms` | Sub-5 ms differences are within noise; not worth the 300 MB download |
| H3 — cold-start not pathological | `16B_cold_start <= 3 × 16A_cold_start` | A 3× slower cold start erases warm-latency gains in short sessions |
| H3 — peak RSS not pathological | `16B_RSS <= 2 × 16A_RSS` | fp16 weights are 2× larger; RSS above 2× signals a leak |

## Interpretation rules

- **H1 FAIL (crash):** CoreML is dead for ModernBERT cross-encoders. Keep
  int8 + CPU as the swap default. Record the error in `results.md`. No code
  change to provider logic. Close experiment as FAIL.
- **H1 PASS, H2 FAIL (loads but slower):** CoreML loads but does not help.
  Keep int8 + CPU. Optionally keep the `RERANK_ONNX_PROVIDER=coreml` escape
  hatch for users who want it. Close as INCONCLUSIVE.
- **H1 PASS, H2 PASS, 16C slower than 16B:** CoreML is the win. Update the
  swap design: fp16 becomes the preferred variant on M-series Macs, with the
  auto-select condition (`"model_fp16" in onnx_filename` → CoreML EP). Close
  as PASS.
- **H1 PASS, H2 PASS, 16C also beats 16A:** fp16 precision is the win, not
  CoreML. Update the swap design to prefer fp16 on CPU. CoreML stays off.
  Close as PASS with caveat.
- **H3 FAIL (footprint pathological):** H2 win is undermined. Keep int8 + CPU
  unless the latency margin is very large. Document the trade-off.

## What to do if the experiment fails

1. **CoreML crash (H1):** document the exact error, keep int8 + CPU default,
   close as FAIL. No follow-up unless a future ORT version fixes dynamic
   shapes.
2. **Inconclusive (H1 pass, H2 noise):** re-run with more iterations (50+) on
   a quiet machine. If still noisy, accept int8 + CPU.
3. **Escalation:** if fp16 + CoreML wins decisively, open a follow-up to test
   it on the swap's retrieval-quality A/B (Exp 9a corpus) to confirm no
   quality regression from the precision change.

## Implementation notes

- **Code path under test:** the benchmark mirrors `rerank()` lines 280–301
  (batch=32, `padding=True`, `truncation=True`, `max_length`,
  `return_tensors="np"`, sigmoid) but loads the model directly via
  `onnxruntime.InferenceSession` with explicit provider control — bypassing
  the singleton so each cell gets a clean session.
- **No env mutation:** the benchmark does not set `RERANK_MODEL` or
  `RERANK_ONNX_PROVIDER`; it controls variant + provider via direct
  `InferenceSession` arguments. This isolates the variable cleanly.
- **Model download:** uses `huggingface_hub.hf_hub_download` (same as
  production). First run downloads ~451 MB; cached thereafter.
- **Known risk:** CoreML EP may silently fall back to CPU for unsupported ops
  without raising. The benchmark records `session.get_providers()` and the
  actual providers list to detect silent fallback.
- **Scope boundary:** latency only. Retrieval quality is the swap A/B's job.

## Cleanup

```bash
# Model files are cached by huggingface_hub in ~/.cache/huggingface — leave
# them; they are reused by the swap A/B. No ChromaDB indexes are created.
# Only remove the run log if desired:
rm -f experiments/16-reranker-coreml-fp16-2026-08-03/output/run_eval.log
```

Keep raw JSON and `results.md`. No large indexes to remove.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `workload.json` | Fixed query-doc workload (10 × 20 pairs, varied lengths) | ✅ |
| `run_eval.py` | Benchmark runner — 3 cells, latency + loadability | ✅ |
| `summarise_eval.py` | Aggregates JSON into `results.md` | ✅ |
| `results.md` | Human-readable result report | ✅ |
| `eval_results.json` | Raw per-cell, per-iteration data | ✅ |
| `output/run_eval.log` | Run log | Optional |
| `analysis.py` | Jupytext percent format — only if JSON warrants plotting | Optional |

## References

- `src/rag_mcp/reranker.py` lines 130–320 — code path under test
- `openspec/changes/swap-reranker-to-gte-modernbert/design.md` Decision 2
- ORT CoreML EP docs: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- Model card: https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base
