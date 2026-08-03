# Experiment 15: gte-reranker-modernbert-base A/B Comparison

**ID**: `15-gte-reranker-swap-2026-07-31`  
**Date planned**: 2026-07-31  
**Operator**: Dr Muhammad Aizat Md Hawari with a-build agent  
**Status**: PLANNED  
**Relation**: OpenSpec change `swap-reranker-to-gte-modernbert`; NiftyPM AIE-20; informs ADR-028

---

## Why this experiment exists

Experiment 10 found that the default reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`,
22.7M params, 512-token context) **degrades technical retrieval by ~27%** on
identifier-heavy queries. ADR-019 disabled the reranker for technical workloads as a
stopgap. The OpenSpec change `swap-reranker-to-gte-modernbert` proposes
`Alibaba-NLP/gte-reranker-modernbert-base` (149M params, ModernBERT architecture,
8,192-token context) as a drop-in replacement. This experiment provides the empirical
evidence to confirm or reject that swap before adoption.

## Hypothesis / Research question

1. **H1 (quality lift)**: gte-reranker-modernbert-base produces ≥ 3pp Coverage@20 lift
   over the rerank-off baseline on FreshStack LangChain (identifier-heavy queries).
2. **H2 (beats MiniLM)**: gte-reranker Coverage@20 ≥ MiniLM Coverage@20 on the same
   corpus.
3. **H3 (baseline gate)**: gte-reranker beats the rerank-off hybrid baseline of 0.738
   Coverage@20 (the threshold from Exp 12).
4. **H4 (latency guardrail)**: gte-reranker P95 latency ≤ 3× the rerank-off P95 latency.
5. **H5 (threshold scaling)**: gte-reranker raw logit distribution does not differ from
   MiniLM by more than 2× in standard deviation (if it does, recalibration is needed).

## Background and prior evidence

- **Exp 10**: MiniLM degrades technical retrieval by ~27%; ADR-019 disabled reranker for
  technical workloads.
- **Exp 12**: Hybrid BM25 with reranker-off achieved 0.738 Coverage@20 on FreshStack
  LangChain. This is the baseline to beat.
- **Exp 9a rerun**: Post-ADR-021 MiniLM reranker with hybrid achieved lower Coverage@20
  than rerank-off on identifier-heavy queries.
- **ADR-021**: ÷30 threshold scaling factor calibrated for MiniLM logits.
- **External benchmarks**: gte-reranker-modernbert-base matches 1.2B Nemotron on Hit@1
  (83.0%), +47% F1 over MiniLM on BTZSC (arXiv:2603.11991).

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Reranker model | off (baseline), MiniLM, gte-reranker-modernbert-base |
| Dependent | Coverage@20 | Primary quality metric |
| Dependent | Hit@1, Hit@5, Hit@10, MRR@10 | Diagnostic quality metrics |
| Dependent | P95 latency | Operational metric |
| Dependent | Raw logit distribution | Threshold scaling assessment |
| Controlled | Corpus | FreshStack LangChain (seed 20260530, ~10,025 docs) |
| Controlled | Retrieval mode | hybrid_bm25 (fixed for all cells) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Post-ADR-021 config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |
| Controlled | `top_k` | 50 |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | FreshStack LangChain (reused from Exp 12) |
| Size | ~10,025 parent docs, 223 queries |
| Categories | 200 identifier-heavy, 20 continuity, 3 semantic |
| Ground truth | `experiments/12-hybrid-default-promotion-2026-06-29/ground-truth.json` |
| Indexes | Reused from Exp 12 (`output/chroma_hybrid_bm25/`) |
| Evidence density | 100% (FreshStack qrels) |

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Embedding model | `qwen3-embedding:0.6b` (Ollama) |
| Reranker (cell A) | None (rerank-off) |
| Reranker (cell B) | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX, cached) |
| Reranker (cell C) | `Alibaba-NLP/gte-reranker-modernbert-base` (ONNX, 151MB download on first use) |
| Hardware | macOS ARM (Apple Silicon) |

```bash
uv sync
ollama list  # verify qwen3-embedding:0.6b is available
```

## Experimental design / cell matrix

| Run ID | Purpose | Reranker | RERANK_MODEL | Expected interpretation |
| --- | --- | --- | --- | --- |
| `hybrid_off` | Baseline | off | _(none)_ | The rerank-off hybrid baseline (Exp 12 reference) |
| `hybrid_minilm` | Current default | on | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Expected to degrade on identifier-heavy queries (per Exp 10) |
| `hybrid_gte` | Candidate | on | `Alibaba-NLP/gte-reranker-modernbert-base` | Expected to beat both baseline and MiniLM |

All cells use `hybrid_bm25` retrieval mode with post-ADR-021 fetch pool config.

## Metrics

### Primary metrics

- Coverage@20 (all queries + identifier-heavy subset)
- Hit@1 (primary precision metric for the AIE-20 benchmark comparison)

### Diagnostic metrics

- Hit@5, Hit@10, MRR@10
- P50/P95 latency
- Raw logit distribution (mean, std dev, min, max, percentiles)

## Procedure / reproduction commands

### Step 1: Reuse indexes from Exp 12

```bash
# Symlink the hybrid index from Exp 12 (avoids rebuilding ~10K docs)
ln -s ../../12-hybrid-default-promotion-2026-06-29/output/chroma_hybrid_bm25 \
  experiments/15-gte-reranker-swap-2026-07-31/output/chroma_hybrid_bm25
```

### Step 2: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/15-gte-reranker-swap-2026-07-31/run_eval.py \
  --resume \
  2>&1 | tee experiments/15-gte-reranker-swap-2026-07-31/output/run_eval.log
```

### Step 3: Record raw logit distributions

```bash
uv run python experiments/15-gte-reranker-swap-2026-07-31/record_logits.py
```

### Step 4: Summarise

```bash
uv run python experiments/15-gte-reranker-swap-2026-07-31/summarise_eval.py
```

## Success criteria / pass gates

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| gte Coverage@20 > rerank-off | ≥ 0.738 (Exp 12 baseline) | Must beat the rerank-off hybrid baseline |
| gte Coverage@20 > MiniLM | ≥ MiniLM Coverage@20 | Must be better than the current default |
| gte Coverage@20 lift over rerank-off | ≥ 3pp | Meaningful improvement worth the larger download |
| Latency guardrail | gte P95 ≤ 3× rerank-off P95 | Operational constraint |
| Logit std dev ratio | ≤ 2× MiniLM std dev | If exceeded, threshold recalibration is needed |

## Interpretation rules

- If all gates pass: **ADOPT** gte-reranker-modernbert-base as default. Flip ADR-028 to
  Accepted. Complete the OpenSpec change.
- If gte beats rerank-off but not MiniLM: **INCONCLUSIVE** — the model is better than
  no reranking but doesn't clearly beat MiniLM. Keep MiniLM as default.
- If gte doesn't beat rerank-off baseline: **REJECT** the swap. The model doesn't help
  on this corpus. Document negative result.
- If logit std dev ratio > 2×: Run threshold recalibration experiment (Exp 1 protocol)
  before final adoption.

## What to do if the experiment fails

1. Document negative result; keep MiniLM as default; update ADR-028 to Rejected.
2. Try a harder corpus (Qasper) to see if the model helps on academic PDFs.
3. Consider alternative models (bge-reranker-v2-m3, jina-reranker-v2) as follow-up.

## Implementation notes

- Code path under test: `rag_mcp.reranker.CrossEncoderReranker.rerank()`
- The reranker model is switched between cells by patching
  `rag_mcp.reranker.RERANK_MODEL` and resetting `CrossEncoderReranker._instance = None`.
- The gte-reranker model downloads 151MB on first use (cell C). Subsequent runs use the
  cache.
- The ÷30 threshold scaling (ADR-021) is applied unchanged in all rerank-on cells.
- Known risk: the gte model's logit distribution may differ from MiniLM, affecting
  threshold filtering behaviour.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable result report | ✅ |
| `run_eval.py` | Evaluation runner (3-cell A/B) | ✅ |
| `record_logits.py` | Raw logit distribution recorder | ✅ |
| `summarise_eval.py` | Results summariser | ✅ |
| `eval_results.json` | Raw per-query results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |
| `logit_distributions.json` | Raw logit stats per model | ✅ |
| `output/run_eval.log` | Run log | Optional |

## References

- Exp 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/`
- Exp 12: `experiments/12-hybrid-default-promotion-2026-06-29/`
- ADR-019: Disable Reranker for Technical Workloads
- ADR-021: Reranker Inference Optimisation (÷30 threshold scaling)
- ADR-028: Swap Default Reranker to gte-reranker-modernbert-base (Proposed)
- OpenSpec: `openspec/changes/swap-reranker-to-gte-modernbert/`
- Benchmark: arXiv:2603.11991 (BTZSC, +47% F1 over MiniLM)
