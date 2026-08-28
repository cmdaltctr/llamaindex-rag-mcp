# ADR-019: Disable Reranker for Technical Workloads (Supersedes ADR-018)

**Status**: Accepted
**Date**: 2026-06-01
**Deciders**: Dr Muhammad Aizat Bin Md Hawari
**Supersedes**: [ADR-018: Balanced Retrieval Defaults](./018-balanced-retrieval-defaults.md)
**Related experiments**: Experiment 9a, Experiment 10

## Context

ADR-018 promoted a balanced retrieval profile with `RERANK_ENABLED=true` as
the default, based on Qasper-style evidence retrieval benchmarks (Experiments
7a and 8a). That evidence remains valid for Qasper-like academic QA, where the
cross-encoder reranker can improve precision and evidence coverage on mostly
semantic, natural-language queries.

Experiment 9a (`experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`)
then showed a different behaviour on technical documentation. On a FreshStack
LangChain corpus of 10,025 parent documents, hybrid BM25 + RRF improved
first-stage retrieval, but applying `cross-encoder/ms-marco-MiniLM-L-6-v2`
reranking degraded both dense and hybrid retrieval.

Experiment 10 (`experiments/10-reranker-technical-workload-calibration-2026-05-31/`)
was intended to test whether this was merely a small-pool problem by sweeping
labelled `RERANK_MAX_FETCH` values 50, 200, and 500. The corrected
interpretation is more nuanced: because the evaluation requested `top_k=50`
and used `RERANK_FETCH_MULTIPLIER=10`, all reranker-on cells resolved to the
same effective fetch size:

```text
fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)
fetch_k = max(50/200/500, 50 * 10)
fetch_k = 500
```

Therefore Experiment 10 does **not** prove that pool size is irrelevant and
does **not** validly compare effective pools of 50, 200, and 500. It does,
however, show that even with a wide effective candidate pool of 500, the current
cross-encoder reranker substantially underperforms rerank-off retrieval on the
FreshStack technical workload.

## Decision

Disable the current reranker by default, replacing ADR-018's global
`RERANK_ENABLED=true` default with:

```text
CHUNK_OVERLAP=100
RERANK_ENABLED=false
TOP_K=10
RERANK_ENABLED_FOR_SEMANTIC=true
HARD_TECHNICAL_THRESHOLD=0.3
```

`CHUNK_OVERLAP=100` and `TOP_K=10` remain from ADR-018. The only default policy
change is that reranking is no longer globally enabled.

`RERANK_ENABLED=false` makes reranking opt-in rather than the default precision
stage.

`RERANK_ENABLED_FOR_SEMANTIC=true` is a retrieval policy knob: when global
reranking is disabled, the system conditionally enables reranking for queries or
workloads that are below the configured technical threshold. This preserves a
path to the Qasper-style benefit measured in Experiments 7a and 8a while still
protecting identifier-heavy technical workloads.

`HARD_TECHNICAL_THRESHOLD=0.3` is a conservative policy heuristic, not an
experimentally calibrated threshold. Experiment 10 tested a corpus with roughly
89.7% identifier-heavy FreshStack queries; it did not sweep technical-query
fractions. The 30% threshold is chosen to avoid applying a known-harmful
reranker to mixed technical corpora until a better calibration exists.

Users who know their corpus is semantic can still set `RERANK_ENABLED=true`
explicitly. Future work on a technical-document reranker may justify changing
this default again.

## Configuration

```python
TOP_K = int(os.getenv("TOP_K", "10"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANK_ENABLED_FOR_SEMANTIC = os.getenv("RERANK_ENABLED_FOR_SEMANTIC", "true").lower() == "true"
HARD_TECHNICAL_THRESHOLD = float(os.getenv("HARD_TECHNICAL_THRESHOLD", "0.3"))
```

The semantic/technical conditional policy is implemented in retrieval-side code
via a central policy resolver. Explicit `rerank=True` and `rerank=False` always
override the policy; omitted rerank requests use `RERANK_ENABLED` first, then
the semantic/technical classifier and optional workload technical-fraction
metadata.

## Evidence

### Experiment 10 key results (FreshStack LangChain, all 223 queries)

| Config | Effective fetch_k | Coverage@20 | Recall@50 | Hit@10 | MRR@10 | Mean ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid_bm25, rerank off | 50 | **0.738** | **0.549** | **0.825** | **0.578** | **753** | **2,218** |
| hybrid_bm25, labelled pool=50 | 500 | 0.540 | 0.354 | 0.596 | 0.346 | 14,346 | 24,765 |
| hybrid_bm25, labelled pool=200 | 500 | 0.540 | 0.354 | 0.596 | 0.346 | 14,892 | 25,059 |
| hybrid_bm25, labelled pool=500 | 500 | 0.540 | 0.354 | 0.596 | 0.346 | 14,365 | 25,006 |

The meaningful comparison is rerank-off versus rerank-on at effective
`fetch_k=500`. On hybrid retrieval, reranking reduces Coverage@20 from 0.738
to 0.540 (−19.8 pp, −26.8%) and increases mean latency from 753 ms to roughly
14–15 seconds.

The identical aggregate metrics across labelled pool cells are expected because
the effective fetch size was the same. They should not be cited as proof that
pool size has no effect.

### Identifier-heavy subset (n=200)

| Mode | Rerank | Coverage@20 | Recall@50 | Hit@10 | MRR@10 |
| --- | :---: | ---: | ---: | ---: | ---: |
| dense-only | off | 0.677 | 0.486 | 0.775 | 0.482 |
| hybrid_bm25 | off | **0.721** | **0.513** | **0.825** | **0.557** |
| dense-only | on, effective fetch_k=500 | 0.504 | 0.296 | 0.580 | 0.298 |
| hybrid_bm25 | on, effective fetch_k=500 | 0.502 | 0.297 | 0.570 | 0.297 |

This is the primary evidence for disabling reranking by default on technical
workloads. The current reranker reverses the benefit of hybrid BM25 retrieval
and collapses both dense and hybrid modes to substantially lower quality.

### Semantic and continuity evidence

The FreshStack semantic subset has only 3 queries, so it is not enough to make
a broad claim about semantic workloads. The 20 continuity regression queries
also do not constitute a representative semantic benchmark. They do show that
reranking did not degrade that small regression fixture, but they are not strong
evidence for a general semantic reranker policy.

For details, see the corrected report:
[`experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md`](../../experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md).

### Evidence update — Experiment 10b / D17 (2026-08-23)

The repaired factorial campaign
([`experiments/10b-reranker-pool-size-corrected-2026-06-29/`](../../experiments/10b-reranker-pool-size-corrected-2026-06-29/))
re-tested this ADR's core claim with corrected methodology: the Experiment 10
effective-fetch confound is gone (true pools 50/100/150/200/500 verified
distinct by preflight), identities frozen (corpus manifest sha256 `f6e7bb09…`,
LanceDB index per ADR-049), 223 paired queries per cell, bootstrap 95% CIs.

Results confirm and strengthen the decision:

- Reranking degrades Coverage@20 at **every** pool size and both retrieval
  modes. At the policy pool 150: dense −0.0996 [−0.1483, −0.0507]; hybrid
  −0.1346 [−0.1865, −0.0821].
- The best observed pool (50) still loses on hybrid (−0.0783 [−0.1142,
  −0.0436]) and is inconclusive on dense (−0.0327 [−0.0714, +0.0069]).
  Larger pools are monotonically worse.
- New observation (H5): hybrid BM25 beats dense with the reranker off
  (+0.0457 [0.0107, 0.0811]) — recorded as a candidate for a future
  defaults discussion, out of scope for this ADR.
- Latency columns are invalid for guardrail adjudication (ambient machine
  load; see the experiment's deviation record). Quality metrics are
  unaffected.

Policy outcome: **ADR-019 stands unchanged** — reranker disabled by default
and for the `codebase` profile.

One evidence gap is now explicit: the `documents` profile sets
`reranker_enabled: true` (restoring ADR-018's balanced intent for semantic
workloads), but **no experiment in this record has demonstrated reranker
benefit on any workload since the Experiment 10 correction**. D17 measured a
technical corpus only and cannot adjudicate the semantic case. Task 6.3
(Qasper PDF A/B — a semantic corpus) of the
`harden-pipeline-correctness-before-calibration` change is designated as
that setting's first real test; until it reports, the `documents` profile
value rests on the pre-correction Experiments 7a/8a Qasper evidence cited
above and should be treated as provisional.

## Consequences

### Positive

- Default retrieval quality improves for technical workloads by avoiding a
  measured reranker regression.
- Default latency improves substantially for technical/hybrid retrieval because
  the cross-encoder is no longer invoked by default.
- ADR-018's `CHUNK_OVERLAP=100` and `TOP_K=10` are preserved.
- The semantic override knob leaves room to re-enable reranking for
  Qasper-like semantic corpora once detection logic is implemented.

### Negative

- Users with semantic corpora who relied on default reranking must now either
  set `RERANK_ENABLED=true` explicitly or wait for semantic/technical policy
  logic to be implemented.
- `HARD_TECHNICAL_THRESHOLD=0.3` is a heuristic. It should be calibrated in a
  future experiment rather than treated as a proven boundary.
- Retrieval/server/CLI defaults and tests may need follow-up changes to ensure
  public surfaces respect the config default.

### Neutral

- The reranker implementation remains available.
- Existing ChromaDB collections are unaffected.
- `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER` remain unchanged; this ADR
  changes whether reranking is invoked by default, not how its candidate pool is
  computed.

## Alternatives Considered

| Option | Rejected because |
| ------ | ---------------- |
| Keep `RERANK_ENABLED=true` (ADR-018) | Experiment 10 shows reranking at effective `fetch_k=500` degrades FreshStack technical retrieval by ~27% on Coverage@20. |
| Disable reranker permanently, no semantic override | Would throw away the Qasper evidence benefit measured in Experiments 7a and 8a. The `RERANK_ENABLED_FOR_SEMANTIC` knob preserves a path to that benefit. |
| Increase `RERANK_MAX_FETCH` to 200+ and keep reranking | Experiment 10's labelled pool sweep does not prove pool size is irrelevant (effective pool was constant at 500). A corrected experiment would be needed to evaluate pool-size sensitivity. |
| Change global defaults to `RERANK_ENABLED=true` only for `HYBRID_ENABLED=false` | Too fragile. Users would need to understand the interaction between hybrid mode and reranker failure modes. |
| Wait for a technical-document reranker model before changing defaults | The current default is actively harmful on technical corpora. Experiment 10 provides direct, reproducible evidence. The safe default should ship immediately. |
| Keep ADR-018 and add a carve-out without superseding | ADR-018's central claim ("`RERANK_ENABLED=true` → balanced") is now incorrect for the project's primary technical corpus. A new ADR is clearer than a lengthy amendment. |

## Implementation Notes

The following changes are required to realise this ADR:

1. **`config.py`**: `RERANK_ENABLED` default changed to `false`. New settings
   `RERANK_ENABLED_FOR_SEMANTIC` and `HARD_TECHNICAL_THRESHOLD` added. These
   are policy knobs; retrieval-side logic must be added to use them.
2. **`retrieval.py`**: `search()` should honour the new settings. Currently it
   only checks `RERANK_ENABLED`. The semantic/technical conditional policy
   requires retrieval-side logic to classify corpora by technical-query
   fraction, which does not yet exist.
3. **`server.py`**: MCP tool `search_documents()` default `rerank` parameter
   should reflect the config default (currently hardcoded to `True`).
4. **`.env.example`**: Document the new settings.
5. **Tests**: Update tests that assert `RERANK_ENABLED=true` as the default.
   Add tests for the semantic/technical conditional policy once implemented.
6. **Experiment 10 status**: Mark as FAIL for current reranker policy; mark
   pool-size sensitivity as INCONCLUSIVE due to the effective fetch-size
   confound.

### Corrected follow-up experiment

A corrected pool-size sensitivity experiment should either:

- Vary `RERANK_FETCH_MULTIPLIER` to control effective pool size directly, or
- Lower `top_k` so that `top_k * multiplier` is smaller than the labelled
  `RERANK_MAX_FETCH` values, or
- Add a direct `fetch_k` override to the runner so that effective candidate
  pools are actually distinct.

This would allow a valid comparison of effective pools 50, 100, 200, 500.

## References

- ADR-018: [`./018-balanced-retrieval-defaults.md`](./018-balanced-retrieval-defaults.md) — superseded by this ADR
- Experiment 9a: [`../../experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`](../../experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/)
- Experiment 10: [`../../experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md`](../../experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md)
- Experiment 7a: [`../../experiments/7a-chunk-overlap-evidence-2026-05-29/results.md`](../../experiments/7a-chunk-overlap-evidence-2026-05-29/results.md)
- Experiment 8a: [`../../experiments/8a-query-embedding-cache-fullsize-2026-05-29/results.md`](../../experiments/8a-query-embedding-cache-fullsize-2026-05-29/results.md)
- Thakur et al. (2025). *FreshStack: Building Realistic Benchmarks for Evaluating Retrieval on Technical Documents*. arXiv:2504.13128.
- Source changes:
  - `src/rag_mcp/config.py`
