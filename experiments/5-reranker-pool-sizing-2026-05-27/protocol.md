# Experiment 5: Reranker Fetch Pool Sizing Recalibration

**ID**: `reranker-pool-sizing-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-retrieval-quality-improvements` (Tier 2)

---

## What this experiment is for

The Tier 2 OpenSpec change replaces the reranker's candidate pool from
`top_k * 2` (currently 10 candidates for the default `top_k=5`) to a much
larger pool: `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)`. The
proposed defaults are `RERANK_MAX_FETCH=50` and `RERANK_FETCH_MULTIPLIER=10`,
which gives 50 candidates by default — 5× the current pool.

Bigger pool means the cross-encoder reranker sees more candidates and has a
better chance of pulling the right answer to the top. But it also means more
CPU work, so latency goes up. We need to confirm:

1. The latency budget holds: **post-warmup P95 ≤ 500 ms** on the calibration corpus.
2. Accuracy does not regress vs the current `(20, 2)` pool.
3. If `(50, 10)` breaches the latency budget, fall back to `(30, 6)` and document.

This experiment **picks the shipped defaults**. It is mandated by
`openspec/changes/rag-retrieval-quality-improvements/design.md` (Decision 2).

---

## Hypothesis

`fetch_k = max(50, top_k * 10)` improves top-1 retrieval accuracy or holds it
steady relative to the current `top_k * 2` baseline, while keeping the
**post-warmup P95 reranker latency at or below 500 ms** on the existing
calibration corpus and hardware.

---

## Background

The original reranker calibration experiment
(`experiments/1-reranker-threshold-calibration-2026-05-12/`) recorded:

| Metric                   | Vector-only | Vector + Reranker (`top_k * 2 = 10`) |
| ------------------------ | ----------- | ------------------------------------ |
| Mean latency (post-warm) | ~30 ms      | ~85 ms                               |
| P95 latency (post-warm)  | ~40 ms      | ~120 ms                              |

Cross-encoder cost scales roughly linearly with the candidate count. Going
from 10 → 50 candidates means ~5× more reranker work, so we expect post-warm
mean to land in the 250–450 ms range and P95 somewhere below 500 ms — but
this is exactly what the experiment confirms.

The "Wide Net, Tight Filter" pattern motivating the change is documented in:

- Lim, J.S. (2026). *Building production RAG: Wide Net, Tight Filter*.
- Abirami, S. et al. (2025). *Hybrid RRF in production RAG*. Recall@100=0.997.
- See `openspec/changes/rag-retrieval-quality-improvements/proposal.md` for the
  full reading list.

The calibrated `÷30` reranker threshold scaling is **unaffected** by the pool
size. We are changing how many candidates the reranker sees, not how it
scores them.

---

## Variables

| Type        | Variable                                                                  | Values                                                                            |
| ----------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Independent | `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` ⇒ effective `fetch_k`        | `(20, 2)` baseline / `(50, 10)` candidate / `(30, 6)` fallback / `(100, 20)` stress |
| Dependent   | Source accuracy (top-1 from correct document)                              | —                                                                                 |
| Dependent   | Answer accuracy (top-1 contains expected substring)                        | —                                                                                 |
| Dependent   | Mean latency post-warmup (ms)                                              | —                                                                                 |
| Dependent   | P95 latency post-warmup (ms)                                               | —                                                                                 |
| Controlled  | Embedding model                                                            | `nomic-embed-text` (matches Exp 1 lineage)                                        |
| Controlled  | Reranker model                                                             | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX)                                     |
| Controlled  | Calibrated `÷30` threshold scaling                                         | Active                                                                            |
| Controlled  | Similarity threshold                                                       | 0.3 (raw, scaled to 0.01 by the reranker path)                                    |
| Controlled  | Corpus                                                                    | Same 5 fixture documents from Exp 1                                               |
| Controlled  | Query set                                                                  | Same 8 structured queries from Exp 1                                              |
| Controlled  | Hardware                                                                   | Apple Silicon Mac, 16 GB                                                          |
| Controlled  | Warmup queries                                                             | 50 (discarded from latency stats)                                                 |
| Controlled  | Measured queries per config                                                | 200 (8 unique × 25 repeats, randomised order)                                     |

> **Why nomic-embed-text and not qwen3-embedding:0.6b?** This experiment shares
> a corpus and calibration lineage with Exp 1. Keeping the embedding model
> identical makes the comparison apples-to-apples. The pool-sizing decision
> generalises to any embedding model because it is a property of the reranker
> pipeline, not the embedding pipeline.

---

## Environment & Prerequisites

| Requirement   | Version / Value                                              |
| ------------- | ------------------------------------------------------------ |
| Python        | 3.12                                                         |
| Ollama models | `nomic-embed-text`                                           |
| Reranker      | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX, ~23 MB)        |
| Hardware      | Apple Silicon Mac, 16 GB                                     |
| Code branch   | Tier 2 implementation branch with `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER` env vars wired in |

```bash
# Verify prerequisites
ollama list   # nomic-embed-text must be present
uv sync
```

---

## Step 1: Reuse the Exp 1 corpus and queries

This experiment piggybacks on the existing reranker calibration setup:

```
experiments/1-reranker-threshold-calibration-2026-05-12/
├── run_experiments.py    ← extended with a fetch-size sweep
└── ...
```

We extend `run_experiments.py` rather than duplicating the corpus. The 5
fixture documents and 8 ground-truth queries from Exp 1 are sufficient — they
already include the Colosseum query that documents the rare-term failure mode.

**Do not write new queries for this experiment.** The queries from Exp 1 are
already calibrated for this corpus, and using a different set would tangle
two variables (pool size + query distribution).

---

## Step 2: Extend the calibration runner

Modify `experiments/1-reranker-threshold-calibration-2026-05-12/run_experiments.py`
to accept a fetch-size sweep:

```python
SWEEP_CONFIGS = [
    {"max_fetch": 20, "multiplier": 2,  "label": "baseline (top_k * 2)"},
    {"max_fetch": 50, "multiplier": 10, "label": "candidate default"},
    {"max_fetch": 30, "multiplier": 6,  "label": "fallback"},
    {"max_fetch": 100, "multiplier": 20, "label": "stress test"},
]
```

For each config:

1. Set `os.environ["RERANK_MAX_FETCH"]` and `os.environ["RERANK_FETCH_MULTIPLIER"]`
   before importing `rag_mcp.retrieval`.
2. Reset the reranker singleton: `CrossEncoderReranker._instance = None`.
3. Fire 50 warm-up queries (discarded).
4. Fire 200 measured queries (8 unique × 25 repeats, shuffled).
5. Record per-query latency, source-accuracy hit, answer-accuracy hit.

> **Why warmup matters**: the ONNX cross-encoder has a one-shot model load
> (~150 ms cold) and a JIT-style first-pass cost. The first 5–10 queries
> always look slow. Discarding 50 warmup queries is conservative.

> **Why 200 measured queries**: standard error on a 95th percentile drops
> below ~3 % of the mean at n=200. With only 8 unique queries × 25 repeats,
> we mostly measure latency variance, not accuracy variance.

The accuracy numbers come from the 8 unique queries (each query's hit/miss
is the same across repeats — accuracy is not stochastic).

---

## Step 3: Run the sweep

```bash
cd experiments/5-reranker-pool-sizing-2026-05-27

# The runner script delegates to the extended Exp 1 runner.
uv run python run_eval.py
```

The script:

1. Ingests the 5 Exp 1 fixture documents into a fresh temporary ChromaDB.
2. For each of the 4 configs in `SWEEP_CONFIGS`, runs warmup + 200 measured
   queries.
3. Tabulates results to stdout and saves raw data to `eval_results.json`.
4. Compares the candidate default `(50, 10)` against the latency budget.

---

## Step 4: Interpret the results

The script prints a comparison table:

```
┌──────────────────────┬─────────┬───────┬───────┬─────────┬──────────┬──────────┐
│ Config               │ fetch_k │ Src   │ Ans   │ Mean ms │ P95 ms   │ P99 ms   │
├──────────────────────┼─────────┼───────┼───────┼─────────┼──────────┼──────────┤
│ baseline (top_k*2)   │   10    │ 87.5% │ 75.0% │   85    │   120    │   140    │
│ candidate default    │   50    │ 100%  │ 87.5% │  280    │   430    │   480    │
│ fallback             │   30    │ 100%  │ 87.5% │  175    │   255    │   290    │
│ stress test          │  100    │ 100%  │ 87.5% │  490    │   720    │   850    │
└──────────────────────┴─────────┴───────┴───────┴─────────┴──────────┴──────────┘
```

Key questions:

1. **Does the candidate default `(50, 10)` clear P95 ≤ 500 ms?**
   - If yes → ship `(50, 10)`. Update `tasks.md` 2.6 and 2.7 as PASS.
   - If no → fall back to `(30, 6)`. Re-run the experiment to confirm
     `(30, 6)` is also under 500 ms (it almost certainly will be).
2. **Does the candidate default improve accuracy vs baseline?**
   - We expect "yes" on source accuracy (the reranker now sees the Colosseum
     chunk that vector retrieval previously buried). If accuracy does not
     improve at all, the reranker pool change is not earning its latency cost.
3. **Does the stress test `(100, 20)` show further accuracy gains?**
   - Probably not — diminishing returns is the canonical cross-encoder shape.
     If it does, document and consider as a separate follow-up change.

---

## Success Criteria

| Check                                          | Pass condition                                                                                  |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Latency budget                                 | Chosen default config has post-warmup P95 ≤ 500 ms                                              |
| Accuracy non-regression                        | Chosen default config has source-accuracy ≥ baseline `(20, 2)` source-accuracy                  |
| Reranker model unchanged                       | Same `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX model; reranker class signature unchanged       |
| `÷30` threshold scaling intact                 | `experiments/1-...` `run_experiments.py` still asserts the calibrated scaling formula           |
| Decision recorded                              | `results.md` names the chosen `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` defaults explicitly |

If `(50, 10)` clears P95 ≤ 500 ms → that becomes the shipped default. If not
→ ship `(30, 6)`. The design doc allows both outcomes.

---

## What to do if the experiment fails

If even `(30, 6)` breaches P95 ≤ 500 ms — which would mean the cross-encoder
on this hardware is much slower than the 2026-05-12 measurement suggested —
something is wrong. Possible causes:

1. ONNX Runtime is using CPU when it should use the macOS Accelerate framework.
   Check `onnxruntime` providers via `rt.get_available_providers()`.
2. The reranker singleton is being recreated per query (model load on hot path).
   Confirm `CrossEncoderReranker._instance` is reused.
3. Background system load (Spotlight indexing, Time Machine). Re-run with
   activity monitor open.

If none of those apply, lower the multiplier further (e.g. `(20, 4)`) and
re-run. Document the chosen defaults and the breach in `results.md`. This is
a hardware-specific observation; users on faster machines can override via
env var.

---

## Cleanup

```bash
rm -rf ./chroma_db_test
```

---

## References

- `openspec/changes/rag-retrieval-quality-improvements/design.md` — Decision 2
- `openspec/changes/rag-retrieval-quality-improvements/tasks.md` — tasks 2.1–2.7
- `experiments/1-reranker-threshold-calibration-2026-05-12/protocol.md` — corpus and queries reused
- `experiments/1-reranker-threshold-calibration-2026-05-12/results.md` — baseline latency numbers
- Lim, J.S. (2026). *Wide Net, Tight Filter*.
- Abirami, S. et al. (2025). *Hybrid RAG with RRF*. Recall@100 = 0.997.
- AGENTS.md — "The reranker is a singleton" rule (must reset between configs).

---

## Artefacts

| File                  | Description                                                                |
| --------------------- | -------------------------------------------------------------------------- |
| `protocol.md`         | This file — hypothesis, method, reproduction steps                         |
| `run_eval.py`         | Sweep runner (calls into the extended Exp 1 runner)                        |
| `eval_results.json`   | Raw per-query latencies and accuracies for each sweep config               |
| `results.md`          | Comparison table, chosen defaults, decision rationale                      |
