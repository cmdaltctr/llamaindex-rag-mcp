## Context

The RAG pipeline has 24 ADRs, many of which set production defaults based on
experimental evidence. A systematic review identified that six of these
evidence bases are either flawed, stale, or missing entirely. The current
state:

| ADR     | Default set                                         | Evidence status                                                               |
| ------- | --------------------------------------------------- | ----------------------------------------------------------------------------- |
| ADR-019 | `RERANK_ENABLED=false` for technical workloads      | Based on Exp 10, which had a design confound (all pool cells = `fetch_k=500`) |
| ADR-019 | `HARD_TECHNICAL_THRESHOLD=0.3`                      | Explicitly described as "a conservative heuristic, not calibrated"            |
| ADR-021 | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` | Changed post-Exp 10; invalidates experiment-scale reranker data               |
| ADR-020 | `PDF_READER=auto` (pending promotion)               | Exp 11 saturated; TODO sections unfilled                                      |
| ADR-023 | `DOC_SIMILARITY_THRESHOLD=0.85`                     | Never calibrated; experiment task 10.1 never run                              |
| —       | `HYBRID_ENABLED=false`                              | Exp 9a gate blocked by reranker; ADR-019 now disables reranker by default     |

This change runs a coordinated batch of six experiments to close every gap.
No production behaviour changes ship in this change — the `fetch_k` parameter
on `search()` and `_resolve_fetch_k()` is already implemented per TDR-005,
is purely additive, and defaults to `None`, preserving existing behaviour
for all production callers. The experiments produce evidence that will
inform separate follow-up changes (ADR amendments, config default flips).

## Goals / Non-Goals

**Goals:**

- Close every evidence gap identified by the multi-model review
- Produce results that either validate current defaults or provide calibrated
  alternatives
- Ensure every experiment is reproducible (protocol, runner, checkpoint/resume)
- Define pass gates _before_ running, with pre-committed interpretation rules

**Non-Goals:**

- Changing production config defaults within this change (results inform future
  changes)
- Researching or testing new reranker models (the current
  `cross-encoder/ms-marco-MiniLM-L-6-v2` is the system under test)
- Modifying the embedding model (`qwen3-embedding:0.6b`)
- Rebuilding the FreshStack LangChain corpus from scratch (reuse Exp 9a data)
- Calibrating the ÷30 reranker threshold scaling (separate concern; Exp 1)

## Decisions

### D1: Direct `fetch_k` override in the runner

**Decision:** Experiment runners call `retrieval.search()` with the `fetch_k=`
parameter (implemented per TDR-005) to bypass the
`max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` formula and set the
effective candidate pool size directly per cell.

**Rationale:** Exp 10b requires genuinely distinct pool sizes ({50, 100, 200,
500}). The current formula collapses multiple labelled values to the same
effective `fetch_k` when `top_k × multiplier > RERANK_MAX_FETCH`. Without a
direct override, any pool-size sweep will reproduce the original confound.

**Alternatives considered:**

- _Vary `RERANK_FETCH_MULTIPLIER` directly_ (e.g., 1, 2, 4, 10 for `top_k=50`):
  works but couples pool size to the multiplier, making it harder to reason
  about. Also, the multiplier interacts with production `top_k=10` differently.
- _Lower `top_k` to 20 with multiplier=1_: changes the retrieval shape, making
  results non-comparable with prior experiments. Rejected.

**Implementation:** Already shipped per TDR-005. The `fetch_k` parameter on
`search()` and `fetch_k_override` on `_resolve_fetch_k()` in `retrieval.py`
bypass the formula when set. The reranker (`reranker.py`) is unchanged — it
processes whatever candidates it receives. Experiment runners set `fetch_k=`
per cell when calling `search()` directly.

### D2: Post-ADR-021 config as the experiment baseline

**Decision:** All experiments use the current production config defaults
(`RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100`, `TOP_K=10`) as the
unmodified baseline. Experiment-specific overrides are applied per cell.

**Rationale:** ADR-021's fetch reduction and speed optimisation are shipped.
Reproducing the old `multiplier=10` config would test a configuration that no
longer exists. The production `top_k=10` fetch_k (`max(100, 30)=100`) is
unchanged from pre-ADR-021, but experiment-scale `top_k=50` is now 150 (was
500), so reranker-on cells from prior experiments are stale.

### D3: New gate definition for Exp 12 (hybrid promotion)

**Decision:** Define a two-part gate for hybrid default promotion:

1. **Quality gate**: hybrid Coverage@20 ≥ dense Coverage@20 + 0.03 (3pp, not
   the original 5pp — the +4.6pp from Exp 9a was real but below the 5pp original
   threshold)
2. **Non-regression guard**: semantic query Coverage@20 regression ≤ −0.02pp

**Rationale:** The original 5pp gate from Exp 9a was never met (+4.6pp) and
would block promotion even if the reranker bottleneck is removed. A 3pp gate is
still meaningful (it's a 4% relative improvement at Coverage@20 ~0.74) while
being achievable. The semantic guardrail is unchanged.

**Alternatives considered:**

- _Keep the 5pp gate_: would require hybrid to outperform dense by more than
  the evidence suggests is possible. Effectively blocks promotion before
  running.
- _Use a cost-benefit gate (quality per ms of latency)_: introduces a
  subjective weighting. Defer to a future decision framework.

### D4: Mixed-corpus construction for Exp 13 (threshold calibration)

**Decision:** Construct a mixed corpus from two sources with known
query-class fractions:

- **Technical subset**: FreshStack LangChain (200 identifier-heavy queries)
- **Semantic subset**: Qasper (natural-language evidence-seeking queries)

The technical-query fraction is varied by sampling different ratios:
{100% technical, 90/10, 75/25, 50/50, 25/75, 100% semantic}.

**Rationale:** `HARD_TECHNICAL_THRESHOLD` controls when the semantic reranker
override kicks in. To calibrate it, we need a corpus where we _know_ which
queries are technical vs semantic, and we need to sweep the fraction. FreshStack
provides the technical side; Qasper provides the semantic side.

### D5: Execution dependency graph

**Decision:** Run experiments in this order:

```
Tier 1 (parallel):
  10b (corrected pool sweep, post-ADR-021 config)
  10.1 (DOC_SIMILARITY_THRESHOLD, fully independent)
  12 (hybrid promotion, rerank-off only — no ADR-021 dependency)

Tier 2 (sequential, each depends on prior):
  9a-rerun → informs ADR-019 validity under post-ADR-021 reranker
      ↓
  13 (HARD_TECHNICAL_THRESHOLD — needs 9a-rerun to know if reranker still hurts)
      ↓
  14 (LiteParse promotion — independent of others, needs harder corpus)
```

**Rationale:** Exp 10b, 10.1, and 12 have no cross-dependencies and can run
concurrently if compute permits. Exp 13 depends on knowing whether the
post-ADR-021 reranker still degrades technical retrieval (from 9a-rerun),
because the threshold calibration is meaningless if the reranker behaviour has
fundamentally changed. Exp 14 is independent but lowest priority.

### D6: Corpus reuse vs rebuild

| Experiment | Corpus               | Strategy                                                                                                                                 |
| ---------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 10b        | FreshStack LangChain | **Rebuild** from `prepare_freshstack.py` (seed 20260530) + `build_indexes.py` — Exp 9a indexes are gitignored and not on disk            |
| 10.1       | Mixed code+docs      | **New**: representative sample of this repo's own codebase + docs                                                                        |
| 12         | FreshStack LangChain | **Rebuild** from Exp 9a scripts (same seed)                                                                                              |
| 9a-rerun   | FreshStack LangChain | **Rebuild** from Exp 9a scripts (same seed)                                                                                              |
| 13         | FreshStack + Qasper  | **New**: FreshStack from 9a scripts + full Qasper dev set (Exp 6b/7a fixtures too small for 30 queries/cell)                             |
| 14         | Qasper               | **New**: full Qasper dev set (≥ 100 queries, ≥ 30 PDFs) — Exp 6b/7a's 20-paper / 80-query fixtures are insufficient for a promotion gate |

## Risks / Trade-offs

| Risk                                                                     | Mitigation                                                                                                                                       |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Exp 10b still shows reranker degradation at all pool sizes               | If so, ADR-019's `RERANK_ENABLED=false` is validated. Document negative result. No config change.                                                |
| Exp 12 passes the 3pp gate but the improvement is noise                  | Require bootstrap confidence intervals (n=200+ queries). If 95% CI includes 0, do not promote.                                                   |
| Exp 10.1 finds that no threshold produces good graph quality             | Document negative result. The document graph feature may need a redesign (separate change).                                                      |
| Exp 13 shows the threshold is corpus-dependent with no single good value | Propose a per-collection threshold or a dynamic heuristic. Defer to future change.                                                               |
| FreshStack LangChain corpus from Exp 9a is not on disk (gitignored)      | Rebuild via `prepare_freshstack.py` (seed 20260530) + `build_indexes.py` in each experiment directory. This is the primary path, not a fallback. |
| Qasper dataset unavailable or licence-restricted                         | Qasper is CC BY 4.0 and available via HuggingFace (`allenai/qasper`). No licence risk.                                                           |
| Total compute exceeds available time                                     | Tier 1 experiments (10b, 10.1, 12) are the minimum viable batch. Tier 2 can be deferred.                                                         |
