## Why

Six production defaults in the RAG pipeline are currently set by ADRs that rest on flawed, stale, or missing experimental evidence. A multi-model review of all 11 experiments and 24 ADRs (Claude 4.6 Sonnet, Gemini 3.1 High, GLM 5.2 — cross-checked against ground truth in `config.py` and ADR source) identified that:

1. **Exp 10 had a design confound** — all pool-size cells resolved to the same effective `fetch_k=500`, so the pool-size question was never answered (ADR-019).
2. **ADR-021 invalidated prior reranker data** — it changed `RERANK_FETCH_MULTIPLIER` from 10→3 and `RERANK_MAX_FETCH` from 50→100, plus achieved a 10× speedup via CoreML + batching. Every reranker-on cell in Exps 9a, 10, and 11 is now stale for experiment-scale `top_k=50`.
3. **`DOC_SIMILARITY_THRESHOLD=0.85` was never calibrated** — ADR-023 and AGENTS.md explicitly mandate experiment task 10.1, which has never been run.
4. **`HARD_TECHNICAL_THRESHOLD=0.3` is an uncalibrated heuristic** — ADR-019 states verbatim that it is "a conservative policy heuristic, not an experimentally calibrated threshold."
5. **Exp 11 (LiteParse) has unfilled TODO sections** — the executive summary, per-category breakdown, and conclusion are still placeholder text.
6. **Hybrid promotion was blocked by the reranker** — ADR-019 now disables the reranker by default, re-opening the hybrid default-promotion gate that Exp 9a could not answer.

Without these experiments, the project ships defaults that are either untested (graph threshold), based on void experiments (pool size), or stale (all reranker-inclusive data). This change runs a coordinated batch to close every evidence gap.

## What Changes

### Tier 1 — Must Run (foundational validity)

- **Exp 10b**: Corrected reranker pool-size sweep on FreshStack LangChain. Uses post-ADR-021 config with the `fetch_k=` parameter on `search()` (per TDR-005) so cells are genuinely distinct ({50, 100, 200, 500}), bypassing the `max()` formula that caused the original confound.
- **Exp 10.1**: `DOC_SIMILARITY_THRESHOLD` calibration. Sweeps {0.70, 0.75, 0.80, 0.85, 0.90} on a mixed code+docs corpus, measuring cluster coherence, cross-link false-positive rate, and community detection quality. Self-contained — no reranker dependency, runs in parallel with everything else.

### Tier 2 — Should Run (stale data or re-opened gates)

- **Exp 12**: Hybrid default promotion test (post-ADR-019). Tests `{dense, hybrid} × {rerank-off}` on FreshStack LangChain. ADR-019's reranker-off default removed the exact bottleneck that killed Exp 9a's gate. Note: the original 5pp promotion gate will not be met (+4.6pp < 5pp), so a new gate or decision framework must be defined in the protocol.
- **Exp 9a-rerun**: Post-ADR-021 reranker validation. Re-runs the 4-cell grid on FreshStack to determine whether the ADR-019 decision (reranker-off for technical workloads) still holds when the reranker sees 150 candidates instead of 500. This is not about production staleness (production `top_k=10` is unchanged at `fetch_k=100`) — it is about whether the experiment that drove ADR-019 was representative.
- **Exp 13**: `HARD_TECHNICAL_THRESHOLD` calibration. Sweeps {0.1, 0.2, 0.3, 0.5, 0.7} on a mixed technical+semantic corpus to find the threshold where the semantic reranker override preserves benefit without triggering on technical queries.
- **Exp 14**: LiteParse default promotion on a harder corpus. Uses Qasper (academic two-column PDFs) where corpus saturation is unlikely. Completes the unfilled TODO sections from Exp 11. Validates H3 (reranker benefit vs LiteParse) and H2 (speed gate under post-ADR-021 optimisations, ~26s vs original 261s).

## Capabilities

### New Capabilities

- `calibration-experiments`: Coordinated batch of six experiments that validate or calibrate RAG retrieval defaults. Defines experiment IDs, hypotheses, cell matrices, pass gates, dependencies, and interpretation rules for each experiment.

### Modified Capabilities

None at the spec level. These experiments produce evidence that will inform future spec modifications (config default flips, ADR updates). The spec changes themselves will be proposed as separate follow-up changes once results are available.

## Impact

- **Experiments**: Six new experiment directories under `experiments/` (IDs 10b, 10.1, 12, 9a-rerun, 13, 14)
- **Code**: The `fetch_k: int | None` parameter on `search()` and `_resolve_fetch_k()` in `retrieval.py` is already implemented per TDR-005 (`docs/tdr/005-fetch-k-override-for-experiment-pool-sweeps.md`). It bypasses the `max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` formula when set, defaults to `None` (production behaviour unchanged), and is covered by regression tests in `tests/test_rerank_fetch_pool.py`. No further code changes are needed for this change — experiment runners call `search(fetch_k=...)` directly
- **ADRs**: Experiments 10b, 9a-rerun, 13 may result in ADR-019/021 amendments. Exp 12 may result in a new ADR for hybrid default promotion. Exp 14 may result in ADR-020 amendment for LiteParse promotion. Exp 10.1 may result in a new ADR for `DOC_SIMILARITY_THRESHOLD`
- **Config**: Potential default changes pending results: `HYBRID_ENABLED`, `HARD_TECHNICAL_THRESHOLD`, `DOC_SIMILARITY_THRESHOLD`, `PDF_READER`
- **Dependencies**: No new runtime dependencies. FreshStack dataset (`datasets`, `pyarrow`) already used by Exps 9a/10. Qasper dataset needed for Exps 13 and 14 (available via HuggingFace, `allenai/qasper`, CC BY 4.0)
- **Compute**: FreshStack LangChain corpus rebuilt via `prepare_freshstack.py` (seed 20260530, 10,025 docs — original indexes are gitignored). Qasper full dev set for Exps 13 and 14. Estimated total runtime: ~6-8 hours across all experiments with checkpointing (includes index rebuilds)
