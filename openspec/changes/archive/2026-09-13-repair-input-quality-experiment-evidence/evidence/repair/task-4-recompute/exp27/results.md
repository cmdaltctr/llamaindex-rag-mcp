# Experiment 27 Results: Combined candidate path (task 5.4)

**ID**: `27-combined-candidate-path-2026-09-09`  
**Report generated**: 2026-09-10T00:22:23+00:00  
**Status**: COMPLETE (verdict FAIL)  
**Raw data**: the checkpoint files named in `cell_sources` (read-only)

---

## TL;DR / Decision

- **Negative result.** Failed gates: quality_recall_at_5, latency_p95_ms.
- The stacked path is worse than the frozen bar the single-factor
  arms were held to. Ship only the component that passed alone.
- Interaction on R@5 is +0.0118.

## Scope

The FreshStack corpus contains no PDFs, so OCR routing is **not**
exercised here. Its evidence is experiment 24, on a disjoint corpus
of five held-out PDFs. This is the combined *retrieval* path:
model-token chunking plus the candidate query instruction.

## Frozen gate checks (on `combined_candidate`)

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Quality | mean R@5 ≥ 0.231 | 0.223686 (n=223) | ❌ FAIL |
| Regression | identifier-heavy R@10 ≥ 0.2583 | 0.269936 (n=200) | ✅ PASS |
| Latency | query p95 ≤ 2850 ms | 4,790 ms | ❌ FAIL |

Thresholds are read from the frozen [`plan.json`](./plan.json), frozen
2026-09-09 and unchanged. Every value is carried
over from the earlier frozen plans rather than re-derived.

## The 2x2

| Cell | Chunking | Query | Measured | R@1 | R@3 | R@5 | R@10 | MRR@10 | P95 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_production | legacy chars | raw | 2026-09-07 (exp 22) | 12.1% | 19.3% | 25.6% | 32.7% | 57.9% | 1,984 ms |
| instruction_only | legacy chars | instructed | 2026-09-09 (exp 26) | 11.2% | 18.7% | 23.1% | 30.7% | 55.0% | 3,543 ms |
| chunking_only_raw | model tokens | raw | 2026-09-09 (here) | 11.4% | 18.9% | 23.7% | 32.3% | 57.3% | 3,390 ms |
| combined_candidate | model tokens | instructed | 2026-09-09 (here) | 10.6% | 17.2% | 22.4% | 32.0% | 54.1% | 4,790 ms |

`baseline_production` and `instruction_only` are loaded from their
committed checkpoints and re-aggregated with identical metric code;
`chunking_only_raw` and `combined_candidate` were measured in this
experiment, interleaved in one process against the preserved
experiment 25 index. Absolute latency is not comparable across the
measurement dates shown in the table.

## Interaction (monitored, not gated)

- Chunking alone: -0.0193 R@5
- Instruction alone: -0.0246 R@5
- Additive prediction: -0.0440 R@5
- Combined, measured: -0.0322 R@5
- **Interaction term: +0.0118 R@5**

assembled across two indexes and three dates; carries cross-run drift as well as signal. Monitored, never gated.

## Cost (task 5.4 record)

Index build cost is experiment 25's verified 0.974906 request-token
ratio; the index is reused unchanged and not rebuilt. Query cost:

- Mean raw query: 450.27 tokens.
- Mean instructed query: 473.17 tokens (1.05x, +22.9 tokens).
- Counted offline with the pinned tokenizer; no API call.

## Drift cross-check against experiment 25

- Experiment 25 published R@5 (model_token_markdown): 0.236226
- This run's `chunking_only_raw` R@5: 0.236540
- Delta: +0.000314

## Interpretation

A passing combined run does not promote the query instruction.
Only experiment 26's own frozen gates can do that (task 5.5).

## Reproduction

```bash
uv run python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py \
  --out-dir repair/evidence/task-4-recompute/exp27
```

No index is built or written: both measured arms query the preserved
experiment 25 index read-only. This regenerated report never
overwrites the frozen historical artefacts.

## Discussion

### The instruction takes the combined path below the bar

*(Heading corrected 2026-09-10: this section was previously titled "The
combined failure is entirely the instruction". The four-cell table is a
historical comparison across runs, so "entirely" was not supportable;
see the Recovery clarification below.)*

The three arms measured against the frozen quality bar of 0.231:

| Arm | R@5 | Bar | |
| --- | ---: | ---: | --- |
| `chunking_only_raw` | 0.2365 | 0.231 | clears |
| `instruction_only` | 0.2312 | 0.231 | scrapes it |
| `combined_candidate` | 0.2237 | 0.231 | **fails** |

The promoted chunker on its own still clears the bar on a fresh run.
Adding the instruction takes it below. Between the two arms measured in
this experiment nothing else changed: same index, same queries, same
process, interleaved — so the −0.0128 R@5 difference on the model-token
index is a within-run paired comparison that isolates the instruction.
Across all four cells the comparison is historical, and the table as a
whole cannot prove the instruction caused every difference in it.

This is corroboration of experiment 26's rejection, reached on a
different index. The instruction hurt the legacy-chunked corpus by
−0.0246 R@5 and the model-token corpus by −0.0128. Two indexes, two
negative results, no positive one.

### The regression gate passed this time, and that is informative

Identifier-heavy R@10 came in at 0.2699 against the 0.2583 bar — a pass,
where the instruction alone on the legacy index failed at 0.2563.

Read together with the interaction term, the reading is that the
model-token chunker absorbs some of the damage the instruction does to
exact-token lookups. Fewer, fuller chunks give an identifier more
surrounding context to be matched on, so a query vector nudged toward
generic evidence still lands in the right chunk more often. It is a
partial cushion, not a fix: the all-query R@5 still falls.

### The interaction is sub-additive, and it does not rescue anything

- Chunking alone: −0.0193 R@5
- Instruction alone: −0.0246 R@5
- Additive prediction: −0.0440 R@5
- Combined, measured: −0.0322 R@5
- **Interaction: +0.0118 R@5**

The two changes overlap: stacking them costs less than the sum of their
separate costs. That is a mildly encouraging structural fact about the
pipeline and a completely irrelevant one for the decision. The combined
path is still worse than either component alone and worse than the
production baseline. A positive interaction term on two negative main
effects is not a result worth shipping.

The term is monitored rather than gated for the reason the frozen plan
gave: it is assembled from runs on two indexes across three dates, so it
carries cross-run drift as well as signal.

### The latency gate did not discriminate, again

| Arm | Mean | P95 |
| --- | ---: | ---: |
| baseline_production (2026-09-07) | 1,023 ms | 1,984 ms |
| chunking_only_raw (today) | 1,389 ms | 3,390 ms |
| combined_candidate (today) | 1,466 ms | 4,790 ms |

The `chunking_only_raw` arm is the SAME configuration experiment 25
measured at a 2,183 ms p95 on 2026-09-08. Today it reads 3,390 ms.
Same index, same queries, same code — the OpenRouter free-tier endpoint
was slower on 2026-09-09. Experiment 26 saw the same thing from the
other direction, where its raw arm was the slowest of all four at
5,543 ms.

The gate is stated in absolute milliseconds against a baseline measured
on a faster day, so it fails for everything run today. It is recorded as
failed because the frozen rule says so and the rule is not edited after
the fact. It carries no evidence about either change.

### The drift check is the reason to trust the quality numbers

`chunking_only_raw` reproduced experiment 25's published R@5 to
+0.000314 — the same index and queries re-measured a day later. Quality
metrics are stable across days even while latency is not. That is what
makes the quality comparison above trustworthy and the latency
comparison worthless.

### Cost

The index is reused unchanged, so the build cost is experiment 25's
already-verified 0.974906 request-token ratio — no rebuild, no spend.
The query-side cost of the instruction is 22.9 extra Qwen tokens on a
450-token mean query: a 1.05x ratio, negligible either way.

Total spend for this experiment: 446 query embeddings.

### Decision

**No promotion follows from this run.** Per task 5.5:

1. The model-token chunker keeps the promotion experiment 25 earned. Its
   own arm cleared the bar again today.
2. `EMBEDDING__QUERY_INSTRUCTION` keeps its empty packaged default. This
   run is corroboration of experiment 26's rejection, not a second trial
   of it — a passing combined run could never have promoted a component
   that failed its own frozen gate, and a failing one does not deepen
   the rejection beyond what experiment 26 already established.
3. OCR routing is untouched here: the FreshStack corpus has no PDFs.

### What this experiment does not cover

The combined path as shipped includes OCR routing, which this corpus
cannot exercise. Task 5.4's "full candidate path" is therefore measured
in two disjoint halves: retrieval here, PDF extraction in experiment 24.
No run in this change measures all three components against one corpus,
and the change record must not imply otherwise.
