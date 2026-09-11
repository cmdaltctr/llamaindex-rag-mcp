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
