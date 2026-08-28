# Experiment 9 — Technical-query rerank policy threshold

**Template ID:** `example/experiment-9-technical-threshold-policy`  
**Status:** PLANNED / CONDITIONAL  
**Role:** run only if Experiment 8 establishes reranker benefit worth routing selectively

## 1. Research question

Given a reranker that is beneficial for some queries and harmful for others, what `HARD_TECHNICAL_THRESHOLD` best routes queries between rerank-on and rerank-off under the **actual production per-query classifier**?

This design deliberately does **not** run a 5-threshold × 6-workload-fraction grid. Workload composition is an analysis/reweighting factor, not an input that should bypass the per-query classifier.

## 2. Entry criterion

Do not run this experiment unless Experiment 8 shows:

- a practically meaningful positive reranker effect on a pre-registered semantic/less-technical subset or another target document workload; and
- a negative or materially worse effect on technical/identifier-heavy queries.

If reranking is uniformly harmful/negligible, mark this experiment `NOT_WARRANTED` and save the compute.

## 3. Pre-registered hypotheses

- **H1 — policy value:** at least one threshold yields higher mean utility/primary quality than always-off while respecting the technical-regression guardrail.
- **H2 — semantic preservation:** selected threshold retains at least +1pp Coverage@20 (or the Experiment-8-confirmed practical benefit) on the semantic/less-technical block relative to always-off.
- **H3 — technical guard:** selected threshold has no worse than -1pp Coverage@20 relative to always-off on the technical block.
- **H4 — current default:** threshold 0.3 lies in the acceptable threshold set, or evidence supports changing it.
- **H5 — routing fidelity:** observed rerank decisions exactly match the production classifier fraction and threshold rule for every query.

## 4. Experimental unit

One fixed labelled query. Every query is evaluated under:

- forced rerank off reference;
- forced rerank on reference;
- each policy threshold with `rerank=None` and **no `technical_fraction` override**.

This provides the counterfactual outcome envelope needed to determine whether routing helps.

## 5. Manipulated / independent variable

`hard_technical_threshold`:
- 0.1
- 0.2
- 0.3
- 0.5
- 0.7

Reference arms are not threshold levels:
- `force_off`
- `force_on`

### Important

`rerank` MUST be `None` in the five policy cells. Passing `rerank=True` or `False` invalidates a threshold cell because explicit override precedes policy resolution.

## 6. Controlled variables

- exact query set/qrels and query order;
- corpus/index identity;
- retrieval mode chosen from Experiment 8 (freeze one mode for primary calibration; do not mix dense/hybrid as an unregistered factor);
- embedding provider/model;
- reranker backend/model/device;
- top_k and candidate-pool policy fixed to the evidence-backed value from Experiment 8;
- similarity threshold fixed;
- sparse backend if hybrid is selected;
- production `_classify_query_technical()` implementation unchanged during the experiment.

## 7. Blocking / stratification variables

Before execution, calculate and freeze each query's classifier fraction and external query label if available. Create blocks such as:

- classifier fraction `<0.1`;
- `0.1-<0.2`;
- `0.2-<0.3`;
- `0.3-<0.5`;
- `0.5-<0.7`;
- `>=0.7`;
- external semantic vs technical labels as a second reporting stratification.

The same queries appear in every threshold/reference cell.

## 8. Dependent variables

Per query:

- classifier technical fraction;
- policy rerank decision + reason;
- Coverage@20 and secondary retrieval metrics;
- forced-off metric;
- forced-on metric;
- routed-policy metric;
- per-query routing regret relative to the better forced reference (diagnostic);
- latency/reranker invocation count.

Aggregate:

- quality in technical and semantic blocks;
- overall quality under pre-registered workload weightings;
- percentage of queries reranked;
- compute/latency cost.

## 9. Cell matrix

Runtime cells:

| Cell | Mode | Threshold | rerank arg |
|---|---|---:|---|
| OFF | forced reference | n/a | `False` |
| ON | forced reference | n/a | `True` |
| T01 | policy | 0.1 | `None` |
| T02 | policy | 0.2 | `None` |
| T03 | policy | 0.3 | `None` |
| T05 | policy | 0.5 | `None` |
| T07 | policy | 0.7 | `None` |

Only **7 runtime cells**.

## 10. Workload composition analysis — no extra inference cells

If the research question needs 0%, 25%, 50%, 75%, 90%, 100% technical workload mixes, pre-register the weighting/resampling procedure and compute those portfolio outcomes from the same per-query cell results.

For example, construct fixed technical/semantic query pools and bootstrap/reweight them at each target composition. Do not rerun retrieval with a workload-level `technical_fraction` unless a separate experiment explicitly studies that override API.

This reduces compute and prevents query-sample changes from being confounded with threshold changes.

## 11. Corpus / ground truth

Use the exact frozen per-query results identity established for Experiment 8 or another pre-registered mixed workload with sufficient queries near the threshold boundaries. Ensure there are enough queries on both sides of 0.3; otherwise this corpus cannot calibrate that boundary.

## 12. Randomisation / counterbalancing

Evaluate every query in every runtime cell. Counterbalance cell execution order by query index to distribute thermal/cache drift. Forced references should not always run first.

## 13. Repetitions and warm-up

Quality: one complete deterministic result per query/cell after preflight.  
Latency: repeated stratified subset if needed; do not repeat all cells just to estimate latency.

## 14. Preflight assertions

- machine-readable plan contains exactly seven runtime cells;
- T01-T07 call `rerank=None`;
- no `technical_fraction` override is supplied in primary policy cells;
- the runtime-reported classifier fraction is stable for a query across thresholds;
- rerank decision equals `classifier_fraction < threshold` under the configured policy prerequisites;
- forced OFF/ON truly force the intended state;
- corpus/index/backend controls match across cells.

## 15. Abort / invalid-cell criteria

- any policy cell calls explicit rerank override;
- classifier implementation/config changes mid-campaign;
- same query yields different classifier fraction between threshold cells;
- a threshold cell reports a rerank decision inconsistent with its recorded fraction/reason;
- query membership differs across thresholds.

## 16. Success / decision gates

Define an **acceptable threshold** as one satisfying both:

- semantic/less-technical benefit gate >= +1pp vs OFF (or pre-registered Experiment-8-derived margin);
- technical regression >= -1pp vs OFF.

Among acceptable thresholds, select by pre-registered objective, e.g. maximum paired overall Coverage@20 under the target workload weighting, breaking ties toward fewer reranker invocations/lower latency.

Report paired bootstrap CIs for threshold-vs-OFF deltas by relevant block. H4 passes if 0.3 is acceptable; if not, a separate ADR/OpenSpec may propose a new value.

## 17. Analysis plan

1. verify routing fidelity H5;
2. join every policy result to its forced OFF/ON counterfactual;
3. calculate per-query reranker treatment effect (`ON - OFF`);
4. show treatment effect versus classifier fraction;
5. calculate threshold routed outcome;
6. bootstrap queries within pre-registered strata/weighting;
7. compute workload-composition curves offline from the same rows;
8. report quality-cost frontier (% reranked vs quality).

## 18. Threats to validity

- classifier fraction is heuristic and may not correlate perfectly with true technicality;
- few queries near a threshold give weak boundary evidence;
- the chosen reranker/retrieval configuration must remain fixed from Experiment 8;
- workload weighting is a deployment assumption and should be reported explicitly.

## 19. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py --resume
uv run python experiments/<promoted-dir>/summarise_eval.py
```

## 20. Required raw artefacts

- fixed query/qrel set + classifier fractions;
- seven-cell machine-readable plan;
- per-query OFF/ON/T01...T07 results;
- policy reasons/rerank flags;
- workload weighting definitions;
- paired bootstrap output;
- runtime manifests.

## 21. Interpretation rules

- no acceptable threshold -> selective policy has no demonstrated value; prefer simpler always-off policy for this configuration.
- multiple acceptable thresholds -> choose using pre-registered quality/cost objective, not post-hoc narrative.
- 0.3 acceptable -> current default is supported within tested evidence.
- different threshold clearly dominates -> propose change separately.

## 22. Cleanup

Retrieval-only cells reuse immutable index; remove only transient checkpoints/logs after committing raw results.
