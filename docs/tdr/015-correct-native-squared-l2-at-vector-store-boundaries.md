# TDR-015: Correct native squared L2 at the vector-store boundaries

**Date:** 2026-08-19
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** vectordb | adapters | dense-scores | thresholds | stage5

## Context

ADR-047 defines `dense_similarity_v1` as a bounded monotonic L2 transform:
`1 / (1 + distance)` over a native non-negative L2 distance
(`src/rag_mcp/core/vectordb/score.py`, `canonical_score_from_l2`). The
committed Experiment 2 fixtures (Stage 5, task 5.2) encode that geometric
interpretation in `fixtures/qrels.json`.

Experiment 2 v1.0 ran identical ChromaDB and LanceDB cells against those
fixtures and failed H3 (threshold parity): 110 of 300 membership checks
mismatched the pre-registered analytic expectation, identically in both
backends. Ranking parity (H1) and monotonicity (H2) passed, and the two
stores agreed with each other, so the failure pointed at a shared production
contract defect rather than backend noise.

### Root Cause Analysis

Both engines report *squared* L2 for their `l2` metric. Fixture evidence,
identical in both backends' raw rows: doc `[0,1,0,0]` vs query `[1,0,0,0]`
reports native `2.0` (= (√2)²), `[0.5,0,0,0]` reports `0.25`, and
`[-2,0,0,0]` reports `9.0`. The adapters passed that raw value straight into
`canonical_score_from_l2`, so the production canonical dense score was
`1 / (1 + d²)` while the contract and the qrels describe `1 / (1 + d)`.

The symptom was nearly invisible: `d²` is monotone in `d`, so ordering
checks pass, and both engines square identically, so cross-store parity
holds. Only an absolute-scale expectation (H3 membership pinned by the
documented formula) exposed the defect. Locations: `score.py:27-51`
(contract text), `chroma.py` (pass-through of the Chroma `l2` value),
`lancedb.py` (pass-through of Lance `_distance`).

## Decision

Apply the square root at each adapter boundary before the canonical
transform, committed as `7bf16b3` "fix(vectordb): apply sqrt to native L2
before canonical score transform".

- `src/rag_mcp/core/vectordb/chroma.py`:
  `canonical_score_from_l2(math.sqrt(distance), backend="ChromaDB")` with a
  `None` guard; `native_distance` keeps the raw squared value.
- `src/rag_mcp/core/vectordb/lancedb.py`:
  `canonical_score_from_l2(math.sqrt(native_distance), backend="LanceDB")`;
  `native_distance` keeps the raw `_distance` as a diagnostic.
- `src/rag_mcp/core/vectordb/score.py` is NOT modified. The contract text
  was correct; the adapters were lying to it.
- A regression test pins the boundary:
  `tests/test_vectordb_contract.py::test_native_squared_l2_is_rooted_before_canonical_score`
  asserts a native squared distance of `4.0` scores `1 / (1 + sqrt(4)) = 1/3`
  while `native_distance` stays `4.0`.

## Evidence

### v1.0 (failing, unmodified harness)

Executed at `c475852` (dirty tree), harness committed at `98449c3`. H1 PASS,
H2 PASS (monotonicity) with systematic documented-formula deviations, H3
FAIL 110/300, H4 PASS, H5 PASS. The finding was recorded as
`exp2-f1-squared-l2-canonical-score`, not hotfixed inside the experiment.

### Fix

`7bf16b3` changed the two adapters, the ADR-047 wording, and added the
contract regression. `score.py` was untouched.

### v1.1 (passing, unchanged harness)

The byte-identical harness (same as `98449c3`) re-ran at `7bf16b3` against
the SAME corpus, queries, and qrels (sha256 `39919461e937…`, `fad16f2b…`,
`c972fefe…`), committed as `4c29377`. H1–H5 all PASS with 0/300 H3
mismatches. Canonical projections of two full runs are byte-identical
(sha256 `6a19b4bf…`). Raw score evidence: native `2.0` now scores
`0.414214 = 1 / (1 + sqrt(2))`; native `9.0` scores `0.25 = 1 / (1 + 3)`.

## Consequences

### Positive

- Canonical scores now match the documented `1 / (1 + d)` contract, and
  threshold membership matches the analytic expectation.
- Ranking was never broken and stays unchanged (H1 green before and after).
- `native_distance` remains available as a raw diagnostic field.
- The regression test fails if any future adapter passes unrooted squared
  L2 into the transform.

### Negative

- Threshold semantics shift: scores moved from `1 / (1 + d²)` to
  `1 / (1 + d)`. For `d > 1` scores rose; for `0 < d < 1` they fell. Any
  numeric `similarity_threshold` observed or calibrated under the pre-repair
  distribution now means something different.

### Neutral

- The divide-by-30 reranker threshold rule (`policy.py`,
  `similarity_threshold / 30` under rerank) remains unchanged in Stage 5.
  Its empirical fit predates this repair and was evaluated while production
  emitted the buggy squared-distance score distribution. The same configured
  threshold also carries dense-score semantics in the non-rerank path and in
  the reranker-failure fallback (ADR-047 decision 3). The end-to-end meaning
  therefore shifted when dense scores changed from `1 / (1 + d²)` to
  `1 / (1 + d)`. Stage 6 must revalidate the ÷30 operating point and
  recalibrate numeric thresholds before policy changes.

  Obligation tracking (2026-08-22): this revalidation is bound to Stage 6.2
  of the `harden-pipeline-correctness-before-calibration` change — pause
  gate 6.GB.2 MUST record an explicit ÷30 disposition (revalidated,
  recalibrated, or retained-with-rationale) before it closes, and the
  `experiments/EXP_README.md` row for Experiment 13 points back to this
  obligation.

  Discharge (2026-08-23): gate 6.GB.2 records **retained-with-rationale** —
  Experiment 10b/D17 found uniform reranker harm across pools 50–500 on the
  technical corpus, leaving no operating point for which recalibration could
  matter; D17 was not designed to isolate threshold effects. Semantic
  revalidation transfers to task 6.3 (Qasper PDF A/B); if that gate changes
  the documents-profile reranker policy, the ÷30 obligation reopens there.
  Record: `openspec/changes/harden-pipeline-correctness-before-calibration/tasks.md` §6B.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Amend the contract and qrels to `1 / (1 + d²)` | The documented transform and committed ground truth already encode `1 / (1 + d)`; relabelling would keep mis-scaled thresholds and misdescribe both engines' native output. |
| Fix the scale in core retrieval | Core retrieval must not hold backend-specific metric knowledge (ADR-047 adapter ownership). |
| Keep the pass-through and document the deviation | The defect was a silent contract violation; documentation alone leaves thresholds mis-scaled. |

## How to Recognise / Handle This Again

1. Symptom: threshold-membership mismatches that are identical across
   backends while ranking and monotonicity checks pass.
2. Diagnostic: query a known fixture; the canonical score must equal
   `1 / (1 + sqrt(native_distance))`. If it equals `1 / (1 + native_distance)`,
   the adapter is passing a squared distance through.
3. Recovery: apply `math.sqrt` at the adapter boundary, keep
   `native_distance` raw, and add the contract regression test.

## Rollback

Revert `7bf16b3`. This restores `1 / (1 + d²)` canonical scores,
`test_native_squared_l2_is_rooted_before_canonical_score` goes red, and
H3-style threshold mismatches return. The reversion touches only the two
adapters, the contract test, and the ADR-047 wording; `score.py` and
retrieval core are unaffected.

## Revisit Triggers

- A new vector-store backend joins the ABC: verify what its native `l2`
  metric actually reports before wiring the transform.
- A store changes its reported metric semantics.
- Stage 6 calibration lands thresholds outside the expected range.
- Score-kind or threshold documentation drifts from the contract.

## References

- Experiment:
  `experiments/example/experiment-2-dense-cross-store-score-parity/`
  (`results.md`, `results.summary.json`, `plan.json` v1.1,
  `output/v1.1_run1/`).
- Fix commit `7bf16b3`; failing v1.0 commits `c475852` / `98449c3`;
  passing v1.1 commit `4c29377`.
- Contract: `src/rag_mcp/core/vectordb/score.py`; adapters
  `src/rag_mcp/core/vectordb/{chroma,lancedb}.py`; regression
  `tests/test_vectordb_contract.py`.
- Threshold rule: `src/rag_mcp/core/retrieval/policy.py:107`; divide-by-30
  calibration: `experiments/1-reranker-threshold-calibration-2026-05-12/`.
- Related records: ADR-047 (semantic swappability), TDR-014 (experiment
  validity framework, Stage 5 field evidence).
