# Experiment 27 — Combined candidate path (task 5.4)

**ID**: `27-combined-candidate-path-2026-09-09`
**Date planned**: 2026-09-09
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED (validity gates frozen 2026-09-09, task 1.6)
**Relation**: `improve-rag-input-quality-5` task 5.4; experiments 22, 24, 25, 26

## Why this experiment exists

Stage 5 measured each input-quality change on its own. Task 5.4 asks
whether the changes are safe **stacked**. Two of them touch the same
retrieval workload: the model-token Markdown chunker moves chunk
boundaries, and the query instruction moves query vectors. Both tax
exact-token recall first. Measuring them apart cannot show what they do
together.

**In plain terms:** we already know each change alone. This run turns
both on at once and checks the result is still at least as good as
today's shipped setup, and no slower than the cap.

## Scope, stated plainly

The FreshStack corpus contains no PDFs, so the OCR routing change is
**not exercised here**. Its evidence is experiment 24, on a disjoint
corpus of five held-out PDFs. This experiment is the combined
*retrieval* path: model-token chunking plus the query instruction. The
change record must not claim more than that.

## Hypothesis

> With the model-token chunker and the candidate query instruction both
> active, mean R@5 over the 223 queries stays at or above 0.231,
> identifier-heavy R@10 stays at or above 0.2583, and query p95 stays
> within 2,850 ms.

## Design: a 2x2, two cells measured here

| Cell | Chunking | Query | Source |
| --- | --- | --- | --- |
| `baseline_production` | legacy character budget | raw | experiment 22 `hybrid__raw` (loaded) |
| `instruction_only` | legacy character budget | instructed | experiment 26 `candidate_instruction` (loaded) |
| `chunking_only_raw` | model-token | raw | **measured here** |
| `combined_candidate` | model-token | instructed | **measured here** |

`chunking_only_raw` re-measures the arm experiment 25 already published.
It is re-run, not loaded, for two reasons: it pairs query by query with
the combined arm inside one process, and it puts both latency figures in
the same network epoch. Experiment 25's published number becomes a
cross-run drift check.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | query instruction | `raw_none` vs `candidate_instruction` |
| Dependent | mean R@5 (all queries) | promotion gate |
| Dependent | identifier-heavy R@10, query p95 | guard + latency gate |
| Controlled | index | experiment 25 model-token index (preserved; read-only) |
| Controlled | corpus, qrels, queries | experiment 22 (sha `ccd3bc5732d69a37…`) |
| Controlled | retrieval | hybrid RRF k=60, rerank off, top_k 50 |

Not changed: documents, index, chunker, worker, routing. Nothing is
ingested and no index is written.

## Metrics

### Primary (gated, on `combined_candidate`)

- Mean R@5, all 223 queries (>= 0.231)
- Identifier-heavy mean R@10, n=200 (>= 0.2583)
- Query p95 latency (<= 2,850 ms)

### Diagnostic (recorded, not gated)

- The interaction term on R@5, and why it is not gated (see below)
- Mean query request tokens, raw vs instructed — the task 5.4 cost record
- R@1/R@3, MRR@10, α-nDCG@10, Hit@10 per category
- Drift check of `chunking_only_raw` against experiment 25's published arm

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json). Every threshold is
carried over unchanged from the earlier frozen plans so the arms stay
comparable; none is re-derived for this run.

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality | mean R@5 >= 0.231 | 0.255884 − 0.024838; identical to experiment 25's quality gate |
| Regression | identifier-heavy R@10 >= 0.2583 | 0.278862 − 0.020571; identical to experiments 25 and 26 |
| Latency | query p95 <= 2,850 ms | identical to experiments 25 and 26 |

**Monitored, not gated:** the interaction term, query token cost, and
continuity R@10. The 2x2 is assembled from runs on two indexes across
three dates, so the interaction term carries cross-run drift as well as
signal. Query token cost is recorded because task 5.4 asks for it, not
gated: the FreshStack queries average 450 Qwen tokens against a 25-token
instruction prefix, so the added spend is about 5.5% of an already
negligible per-query cost. Continuity R@10 has a ±0.15 half-width at
n=20.

## Interpretation rules

- All three gates pass → the stacked path is safe to ship as a whole.
  This does **not** by itself promote the query instruction: only
  experiment 26's own gates can do that (task 5.5).
- Quality or regression gate fails → the stack is worse than its parts.
  Record it, and ship only the component that passed alone.
- A passing combined run can never rescue a component that failed its
  own frozen gate. Do not tune the instruction text to move this run.

## Procedure

```bash
# 1. Point STORE_URI at the preserved experiment 25 index (read-only).
# 2. Run both arms interleaved with alternating arm order.
uv run python experiments/27-combined-candidate-path-2026-09-09/run_eval.py --resume
# 3. Summarise + gate check + 2x2 assembly
uv run python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py
```

## Cost

Query embeddings only: 223 x 2 calls. No index is built. The index build
cost of the chunking component is experiment 25's already-verified
0.974906 request-token ratio and is not re-measured here.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` / `plan.json` | this plan + frozen gates | ✅ |
| `run_eval.py` / `summarise_eval.py` | runner chain | to write |
| `results.md` + `output/*.json` | outcomes | ✅ |
