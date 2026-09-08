# Experiment 25 — Token-aware chunking ablation (task 5.2)

**ID**: `25-token-chunking-ablation-2026-09-08`
**Date planned**: 2026-09-08
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED → candidate index BUILT (2026-09-08, 6.44 h, 22,281 chunks); cost gate PASSED on corrected accounting (see `output/verify_accounting_*.json`); evaluation cells pending

## Accounting correction (2026-09-08, external review; definitive revision same day)

The original pre-build counter (`token_accounting.py`, deprecated with its
defects documented) was proven wrong: it included the corpus manifest jsonl
production never selects, counted body text rather than the composed
`MetadataMode.EMBED` payload, and its shared additive contamination did not
cancel in the ratio. A second review round then caught that my first
correction reconstructed nodes from row text+metadata — null-valued retained
keys (`content_type: None` on 19,361 baseline nodes, `header_path: None` on
all candidate nodes) rendered into rebuilt payloads and inflated totals by
~0.7–1.2%. The definitive method deserialises the real pre-store nodes from
`metadata["_node_content"]`; it reproduces the audit's reference totals to
the token:

| Side | Files | Chunks | Real payload tokens | Max payload |
| --- | ---: | ---: | ---: | ---: |
| Baseline (exp 22 store) | 10,024 | 32,631 | 13,969,694 | 2,087 |
| Candidate (exp 25 store) | 10,024 | 22,281 | 13,622,856 | 1,120 |

Cost gate (≤ 1.15 × baseline): **0.975 — PASS**. Note: the installed
embedding adapter performs no newline replacement (verified in
site-packages); any "after normalisation" totals are hypothetical. The
defective pre-spend approval path is disabled in `build_index.py`;
`verify_accounting.py` is retrospective verification only (TDR-022).

**Relation**: `improve-rag-input-quality-5` task 5.2; ADR-063 (Proposed); experiment 22 baseline

## Why this experiment exists

The merged model-token-aware Markdown chunker (ADR-063,
`semantic-text-splitter` + Qwen tokenizer) replaces the
characters-per-token estimate for Markdown sources. Its retrieval effect
is unmeasured. This experiment rebuilds the Experiment 22 corpus index
with the candidate chunker and compares on identical queries and qrels,
before any chunk-size default changes.

**In plain terms:** the search index chops documents into pieces. The
new splitter counts words the way the AI model actually does, instead of
guessing. Rebuild the whole index with the new splitter, ask the same
223 questions. Passes if: it finds at least as much as the old splitter
(allowed to be up to 2.5% worse, which is measurement luck), doesn't
cost more than 15% extra in embedding API money, and answers just as
fast.

## Hypothesis

> An index built with model-token-aware Markdown chunking is
> non-inferior to the Experiment 22 baseline splitter (mean R@5 ≥
> 0.2310), keeps identifier-heavy R@10 ≥ 0.2583, and stays within 1.15 ×
> baseline embedded tokens and the query latency cap.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | chunker | `baseline_splitter` vs `model_token_markdown` |
| Dependent | mean R@1/R@3/R@5, identifier-heavy R@10 | gates + task 5.2 metrics |
| Dependent | tokens, chunk-count distribution, ingestion time | cost gate |
| Controlled | corpus, qrels, queries | Experiment 22 (sha `ccd3bc5732d69a37…`) |
| Controlled | embedding | `qwen/qwen3-embedding-4b` via OpenRouter, dims 2560 |
| Controlled | retrieval | hybrid RRF k=60, rerank off, top_k 50 |

Not changed: retrieval stack, worker, routing, query text (raw).

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | Experiment 22 FreshStack LangChain corpus (preserved copy) |
| Local path | `~/Development/DATA/omrg/experiments/freshstack-corpus` (see exp 22 `DATA_LOCATIONS.md`) |
| Size | 10,024 parent documents → baseline 32,631 chunks |
| Ground truth | `experiments/22-.../output/ground-truth.json` (223 queries, fixed) |
| Indexes | new build under `output/lancedb/` (gitignored); baseline index preserved untouched |

## Metrics

### Primary (gated)

- Mean R@5 over all 223 queries (floor 0.2310)
- Identifier-heavy mean R@10, n=200 (floor 0.2583)
- Total embedded tokens vs baseline (≤ 1.15×); query p95 ≤ 2,850 ms

### Diagnostic (recorded, not gated)

- Evidence R@1/R@3, Evidence MRR, section/hierarchy Match@1, nDCG
- Chunk-size distribution; chunks carrying derived `header_path` per path
- Worst-case gap: chunk-text tokens vs full embedding-payload tokens
- Ingestion wall-clock; resolved tokenizer identity **and revision** in the manifest

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json). Every threshold is
baseline minus measured noise (`gate_noise.json`, N=10,000, seed
20260908): paired R@5 95% half-width 0.024838; R@10 half-width 0.020571;
hybrid p95 estimator CI [1,518.9, 2,334.3] ms.

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality (non-inferiority) | Mean R@5 ≥ 0.2310 | 0.255884 − 0.024838 |
| Regression | Identifier-heavy R@10 ≥ 0.2583 | 0.278862 − 0.020571; at-risk: heading prefixes, identifier splitting |
| Cost | Tokens ≤ 1.15 × baseline; query p95 ≤ 2,850 ms | baseline tokens recomputed with the same counter at run time; 1.5 × p95 clears the estimator CI |

**Monitored, not gated:** continuity R@10 (n=20; bootstrap half-width
±0.15 — a hard gate would be noise; reason recorded in the plan).

## Interpretation rules

- All gates pass → candidate eligible per task 5.5; promotion judged on lift + cost together.
- Quality floor missed but regression holds → negative result; keep current splitter defaults; ADR-063 stays Proposed.
- Regression gate fails → chunker damages exact-token recall; investigate header-path prefix cost before any re-run.
- Cost gate fails → token budget exceeded; inspect chunk-size distribution; do not relax the ratio.

## Procedure

```bash
# 1. Recompute baseline embedded-token total (same tokenizer counter)
#    and record it in the runtime manifest BEFORE building.
# 2. Build candidate index (isolated, gitignored output/)
uv run python experiments/25-token-chunking-ablation-2026-09-08/build_index.py --resume
# 3. Run cells (baseline cell may reuse exp 22 checkpoints only if the
#    runtime manifest matches; otherwise rerun)
uv run python experiments/25-token-chunking-ablation-2026-09-08/run_eval.py --resume
# 4. Summarise + gate check
uv run python experiments/25-token-chunking-ablation-2026-09-08/summarise_eval.py
```

## Cleanup

Candidate LanceDB index under `output/lancedb/` is gitignored; delete or
preserve per reuse value (baseline index at the DATA location stays
untouched). Raw JSON and summaries are committed.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` / `plan.json` | this plan + gates | ✅ |
| `build_index.py` / `run_eval.py` / `summarise_eval.py` | runner chain | to write |
| `results.md` + `output/*.json` | outcomes | ✅ |
