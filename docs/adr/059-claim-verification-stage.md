# ADR-059: Claim Verification Is an Opt-In Cloud Judge

**Date:** 2026-09-04
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The grounded answering pipeline (ADR-057) proves citations
referentially: an ordinal resolves to stored lineage. Security review
F4 (`add-grounded-answer-synthesis-3`) recorded the limit — a valid
ordinal does not prove the cited evidence entails the claim. An
unsupported claim followed by `[1]` returns `status="ok"` because the
parser checks the ordinal, never the semantics.

Experiment 20 (`experiments/20-citation-faithfulness-2026-09-02/`,
PASS, 120 claim–evidence triples) measured whether an LLM judge closes
that gap:

| Metric | GLM-5.3 judge | Lexical baseline | Gate |
| --- | ---: | ---: | --- |
| Unsupported-claim recall | 1.000 | 0.617 (0.000 on contradicted) | ≥ 0.80 |
| False rejection | 0.000 | 0.017 | ≤ 0.10 |
| P95 latency per claim | 3.33 s | 0.02 ms | ≤ 5 s |
| Unparseable | 0.0% | 0.0% | report |

A DeepSeek V4 Flash 0731 cross-judge agreed with GLM-5.3 on all 120
triples. All pre-registered gates passed (H1 recall/false rejection,
H2 lexical gap ≥ 0.20, H3 latency). The lexical baseline's 0.0 recall
on contradicted claims shows the task needs semantic judgement, not
token overlap.

## Decision

Add an **optional claim-verification stage** to the answer pipeline,
injected through the completion-seam pattern ADR-057 established: the
composition root builds the judge
(`compose.build_verify_llm`, applying `verify_model` /
`verify_provider`) and the transport injects it as an async seam.
`core/answer/verify.py` owns the stage; no LLM object and no settings
singleton reach `core/` (ADR-037).

1. **Opt-in, off by default.** `ANSWER__VERIFY_CLAIMS=false` is the
   default. Disabled, the referential-only `ok` guarantee is
   unchanged — zero behavioural difference for existing deployments.
2. **Cloud by explicit choice.** The experiment showed a local
   `qwen3:4b` judge infeasible on consumer hardware, so the judge
   needs a cloud model. This is an explicit opt-in against ADR-024's
   local-first policy, priced at one judge call per cited claim
   (P95 ≈ 3.3 s each on GLM-5.3).
3. **Graceful degradation, always.** Provider unavailable, network
   error, or all-unparseable verdicts → `verification_skipped` with a
   reason; the referential-only `ok` status is retained; the pipeline
   never raises and never blocks an answer behind a cloud dependency
   the operator has not configured.
4. **Honest statuses.** Every cited claim supported → keep `ok`, add
   `verified: true`. Any unsupported (or unparseable) claim →
   `status="unverified_claims"` with the failing claims listed; answer
   text, citations, and evidence are all retained so the caller
   decides. Verification never silently passes an unverifiable claim.
5. **Injection-resistant judge.** Evidence text is untrusted. Each
   evidence block is wrapped in explicit `<evidence>` delimiters,
   labelled as untrusted source data, and the instruction hierarchy is
   repeated after every block — an injected instruction inside a cited
   chunk cannot flip the verdict.
6. **Settings and profiles.** `ANSWER__VERIFY_CLAIMS`,
   `ANSWER__VERIFY_MODEL` (empty = provider default model), and
   `ANSWER__VERIFY_PROVIDER` (aliases `cloud`/`local` resolve to the
   configured backends; otherwise a literal registry name, validated
   at startup). Profile bundles may override the three verify keys per
   collection — the one answer-block carve-out that is
   profile-scoped — with env vars still winning over the profile. No
   shipped profile enables verification.

## Consequences

* F4 moves from open residual to mitigated: the referential guarantee
  gains an optional semantic check, and every result states which
  guarantee it carries (`verified`, `unverified_claims`,
  `verification_skipped`, or plain `ok`).
* Diagnostics report `verification_ms` and `verification_calls`
  separately from `retrieval_ms` / `generation_ms`, so the judge's
  latency cost is visible per answer.
* The judge adds no new dependency: it reuses the `OpenAILike` cloud
  provider path the answer pipeline already uses.
* Experiment caveats carry forward: the corpus is entity-disjoint per
  file (the swapped class had one related-file pair — perfect swapped
  detection may not generalise to topically related evidence); 120
  triples is small, and perfect accuracy may indicate corpus
  saturation; a pipeline-derived faithful-claims validation set
  remains required before any deployment decision built on H1.
