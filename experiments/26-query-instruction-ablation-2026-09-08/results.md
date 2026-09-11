# Experiment 26 Results: Query-instruction ablation (task 5.3)

**ID**: `26-query-instruction-ablation-2026-09-08`  
**Date run**: 2026-09-09  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: FAIL  
**Raw data**: [`output/cells/`](./output/cells/)

---

## TL;DR / Decision

- **Negative result.** Failed gates: quality_paired_r5_lift, regression_identifier_r10, latency_p95_ms.
- Paired mean R@5 lift is -0.0246 against a frozen requirement of
  +0.0300.
- Per task 5.5 the packaged default for `EMBEDDING__QUERY_INSTRUCTION`
  stays empty. The instruction text is not tuned to chase the gate.

## Frozen gate checks

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Quality | paired mean R@5 lift ≥ +0.0300 | -0.0246 (95% half-width ±0.0155, n=223) | ❌ FAIL |
| Regression | identifier-heavy R@10 ≥ 0.2583 | 0.2563 (n=200) | ❌ FAIL |
| Latency | query p95 ≤ 2850 ms | 3,543 ms | ❌ FAIL |

Thresholds are read from the frozen [`plan.json`](./plan.json); no
threshold lives in the summariser. The gates were frozen on
2026-09-08 and are unchanged.

## Raw arm (`raw_none`)

| Category | n | R@1 | R@3 | R@5 | R@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 223 | 12.1% | 19.3% | 25.6% | 32.7% | 57.9% |
| identifier-heavy | 200 | 6.5% | 14.5% | 20.0% | 27.9% | 57.0% |
| semantic | 3 | 0.0% | 2.0% | 3.9% | 7.8% | 16.7% |
| continuity | 20 | 70.0% | 70.0% | 85.0% | 85.0% | 73.2% |

## Instructed arm (`candidate_instruction`)

| Category | n | R@1 | R@3 | R@5 | R@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 223 | 11.2% | 18.7% | 23.1% | 30.7% | 55.0% |
| identifier-heavy | 200 | 5.5% | 13.3% | 17.7% | 25.6% | 53.7% |
| semantic | 3 | 0.0% | 2.0% | 3.9% | 7.8% | 16.7% |
| continuity | 20 | 70.0% | 75.0% | 80.0% | 85.0% | 73.5% |

## Candidate instruction

```text
Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.
```

## Latency

| Arm | Mean | P95 |
| --- | ---: | ---: |
| raw_none | 1,752 ms | 5,543 ms |
| candidate_instruction | 1,531 ms | 3,543 ms |

Both arms ran interleaved in one process with alternating arm order.
*(Note 2026-09-10: execution periods were not recorded for this
historical run, so a single uninterrupted network period cannot be
claimed from the data; only the arm-order alternation is recorded.)*
Latency is cloud-inclusive. The first query of the run pays the
one-off BM25 index build; that cost lands on the raw arm, which ran
first (`arm_position` 1), which if anything works against the
baseline rather than for the candidate.

## Drift cross-check against Experiment 22

- Experiment 22 published R@5 (hybrid, raw): 0.255884
- This run's raw arm R@5: 0.255884
- Delta: +0.000000

Same index, same 223 queries. *(Note 2026-09-10: an equal aggregate
does not show rank-level stability — 65 of the 223 per-query rankings
differ from Experiment 22's run; see the corrected discussion below.)*
The gate is evaluated against this
run's own raw arm, which is paired query by query with the
instructed arm; Experiment 22's number is a drift check only.

## Monitored, not gated

- Continuity R@10 (n=20): raw 0.8500 → candidate 0.8500. The bootstrap
  95% half-width at n=20 is ±0.15, so no hard gate could be meaningful.

## Reproduction

```bash
uv run python experiments/26-query-instruction-ablation-2026-09-08/run_eval.py --resume
uv run python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py
```

*(Reproduction note 2026-09-10: the commands above are the historical
ones. As of the repair change, `run_eval.py` no longer resumes the
historical checkpoints — measured runs need `--run-dir <name>`, smoke
runs use `--limit`, and the summariser writes to an explicit
`--out-dir` instead of this file.)*

No index is built or written: both arms query the preserved
Experiment 22 index read-only.

## Discussion

### The quality result is real, not noise

The paired R@5 lift is −0.0246 with a paired bootstrap 95% half-width of
±0.0155. The degradation is larger than its own noise band, so this is
not a wash: the instruction actively hurt this workload. It also missed
the frozen requirement of +0.0300 by more than the whole gate.

The same pattern runs through every cutoff and both arms of the
comparison. R@1 12.1% → 11.2%, R@3 19.3% → 18.7%, R@10 32.7% → 30.7%,
MRR@10 57.9% → 55.0%. Nothing improved.

### The regression gate confirms the mechanism the plan predicted

The frozen plan named the risk before the run: "an instruction preamble
dilutes identifier tokens, taxing exact-token recall first." That is
what happened. Identifier-heavy R@10 fell from 27.9% to 25.6%, and
identifier-heavy R@5 fell further in relative terms than the all-query
figure: 20.0% → 17.7% is a 11.3% relative drop, against 9.6% overall.

The size of the effect is the surprise. These are not short queries:
the mean FreshStack query is 450 Qwen tokens, and the full instruction
prefix (`Instruct: … \nQuery: `) is 25. A 5.5% addition to the token
count moved R@5 by 2.5 points. Dilution is therefore the wrong mental
model for what happened — the instruction is not crowding out identifier
tokens by volume. It is steering the query vector toward a generic
"find supporting evidence" region of the space, and on a workload where
the match is decided by an exact identifier, that steering is the whole
problem.

FreshStack is a code-and-docs workload: 200 of the 223 queries are
identifier-heavy.

### The latency gate did not discriminate

Read this one carefully before drawing a conclusion from it.

| Arm | Mean | P95 |
| --- | ---: | ---: |
| raw_none | 1,752 ms | 5,543 ms |
| candidate_instruction | 1,531 ms | 3,543 ms |

The **raw** arm is the slower of the two, and it breaches the 2,850 ms
cap by more than the candidate does. Both arms ran interleaved in one
process with alternating order, so arm-order bias is controlled — but
that does not identify why the absolute numbers are high. The gate is
stated in absolute milliseconds against a baseline p95 measured on
2026-09-07, two days before this run. The gap between the two dates is
consistent with a slower provider period, yet these measurements cannot
separate provider-side variance from any other cause, so none is
claimed. Absolute latency comparisons across dates are inconclusive.

The honest reading: the latency gate did not discriminate. It is
recorded as failed because that is what the frozen rule says, and the
rule is not edited after the fact. It carries no evidence against the
instruction. The quality and regression gates are the ones that decide
this experiment, and both fail on their own terms.

### What the raw arm's agreement with Experiment 22 shows

*(Corrected 2026-09-10: this section previously claimed the equal R@5
proved a deterministic endpoint. It does not, and the ranking-level
comparison below was not made before the claim was written.)*

The raw arm's mean R@5 is 0.255884, identical to Experiment 22's
published figure to six decimal places — while 65 of the 223 per-query
rankings differ between the two runs, first differences starting as
early as rank 1. Equal aggregates over different rankings mean metric
agreement is not evidence of deterministic execution: the exact match of
the mean is partly coincidence, and no claim of endpoint or pipeline
determinism follows from it.

What the agreement does support is comparability at the aggregate
operating point. The −0.0246 paired delta is a within-run comparison —
both arms measured in one interleaved process with the instruction as
the only manipulated factor — and its bootstrap half-width (±0.0155)
is what bounds the noise on that attribution, not the cross-run
aggregate match.

### Decision

**Reject the candidate instruction.** Per task 5.5:

1. `EMBEDDING__QUERY_INSTRUCTION` keeps its empty packaged default.
2. The setting stays available and documented as opt-in. The mechanism
   works; the seam is correct; this particular instruction text is wrong
   for this workload.
3. The instruction text is **not** rewritten and re-run against the same
   gate. Tuning a candidate until it clears a gate it already failed
   turns the gate into decoration. A different instruction is a new
   experiment with its own frozen plan.

### What this does not say

It does not say query instructions are useless. It says one specific
generic-evidence instruction, on a 90%-identifier-heavy workload, with
`qwen/qwen3-embedding-4b`, costs about 2.5 recall points at cutoff 5.
A prose-heavy corpus might behave differently. The three semantic
queries in this set moved not at all, which is exactly what n=3 buys.
