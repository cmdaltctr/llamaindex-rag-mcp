# Experiment <N> Results: <Descriptive Title>

**ID**: `<experiment-directory-name>`  
**Date run**: YYYY-MM-DD  
**Operator**: <human operator> with <AI/build agent, if used>  
**Status**: PASS | FAIL | INCONCLUSIVE | PARTIAL  
**Outcome**: <one-sentence decision, e.g. "Ship as opt-in only; do not flip defaults.">  
**Raw data**: [`eval_results.json`](./eval_results.json) or <external artifact pointer>

---

## TL;DR / Decision

State the result in plain English first.

- Decision: <what should ship / not ship / remain unchanged>
- Winning configuration, if any: `<settings>`
- Main measured effect: `<metric delta>`
- Main caveat: <negative result, saturation, reranker dependency, corpus limit>
- Follow-up required: <yes/no and path>

## Hypothesis / Purpose

Restate the pre-registered hypothesis from `protocol.md`, then say whether it
was supported.

> <Hypothesis copied or summarised from protocol>

Verdict: <supported / not supported / partially supported>.

## Background

Briefly remind readers why the experiment was run. Link to the protocol and any
upstream evidence.

- Protocol: [`protocol.md`](./protocol.md)
- Related experiments: `<path>`
- Related ADR / OpenSpec: `<path>`

## Variables

| Type | Variable | Values actually run |
| --- | --- | --- |
| Independent | <thing changed> | <values> |
| Dependent | <metric> | <metric name / unit> |
| Controlled | <fixed factor> | <value> |

Note any deviations from `protocol.md`. If there were none, say:

> No deviations from the protocol.

## Environment and corpus

| Item | Value |
| --- | --- |
| Python | <version> |
| Models | <embedding/reranker/LLM> |
| Hardware | <machine> |
| Corpus | <documents / records / chunks> |
| Ground truth | <records and evidence density> |
| Key config | `<ENV=value>`, `<ENV=value>` |

Record whether indexes were copied, rebuilt, or generated in temp directories.

## Method / reproduction

Summarise what was actually executed. Include the exact command(s), not just a
description.

```bash
<command used to generate results>
```

If the run has multiple cells, show either the loop or representative commands.
If raw artifacts are external, explain where they are stored and why.

## Results

### Main summary table

| Config / cell | n | Primary metric | Secondary metric | Latency / cost | Notes |
| --- | -: | ---: | ---: | ---: | --- |
| <baseline> | <n> | <value> | <value> | <value> | <note> |
| <candidate> | <n> | <value> | <value> | <value> | <note> |

### Pass/fail against criteria

| Criterion | Threshold | Measured | Pass? |
| --- | ---: | ---: | :--: |
| <criterion from protocol> | <threshold> | <value> | ✅ / ❌ |
| <guardrail> | <threshold> | <value> | ✅ / ❌ |

### Detailed results by phase / category

Use only the subsections that match the protocol.

#### Phase / category 1: <name>

| Run | Setting | Baseline | Candidate | Delta | Interpretation |
| --- | --- | ---: | ---: | ---: | --- |
| `<run-id>` | `<setting>` | <value> | <value> | <delta> | <meaning> |

#### Phase / category 2: <name>

| Run | Setting | Baseline | Candidate | Delta | Interpretation |
| --- | --- | ---: | ---: | ---: | --- |
| `<run-id>` | `<setting>` | <value> | <value> | <delta> | <meaning> |

### Diagnostics

Report measurements that explain the result but may not be pass gates.

- <Diagnostic 1>: <value and interpretation>
- <Diagnostic 2>: <value and interpretation>
- <Named case, if any>: <rank/result>

Common diagnostics:

- source-level vs evidence-level retrieval
- chunk counts and token-estimate distribution
- mean/P95 latency
- cache hit rate and embed-call counts
- per-category rare-term / semantic / mixed performance
- named regression cases

## Analysis

Explain why the result happened. Prefer concrete evidence over speculation.

Useful patterns:

- If the baseline saturated, say what metric/corpus size caused the ceiling.
- If the candidate won only with reranking, say the gain is reranker-driven.
- If a wider `top_k` helps, say whether this changes the production default or
  only an audit/evidence workflow.
- If a negative result is valuable, state what implementation path it rules out.

## Conclusion / Decision

### Decision

State the production or project decision.

```text
<default / config / implementation decision>
```

### What should change

1. <Code/config/doc change to make>
2. <Default to promote or keep unchanged>
3. <ADR/OpenSpec/index update required>

If nothing changes, say explicitly:

> No production code changed. This experiment validates / rejects <thing>.

### What should not change

- <Default not flipped>
- <Implementation path not pursued>
- <Corpus-specific result not generalised>

### Caveats

- <Limitation 1>
- <Limitation 2>

## Follow-ups

Only include follow-ups justified by the measured result.

| Follow-up | Reason | Priority |
| --- | --- | --- |
| <experiment / code change / doc update> | <why> | high / medium / low |

If the experiment failed because of corpus saturation, describe the harder
benchmark required before rerunning.

## Reproduction

Provide a compact copy-paste block for rerunning the final result.

```bash
<minimal rerun command>
```

Raw output is stored at:

```text
<path/to/eval_results.json>
```

## Cleanup

```bash
<cleanup command, if any>
```

Say whether cleanup is optional. Keep raw JSON, summaries, protocols, and
ground truth unless there is a size reason to store them externally.

## Artefacts

| File / directory | Description |
| --- | --- |
| `protocol.md` | Pre-run plan and pass criteria |
| `results.md` | This report |
| `run_eval.py` | Evaluation runner |
| `eval_results.json` or `eval_results.*.json` | Raw results |
| `eval_results.summary.json` | Aggregated summary, if present |
| `ground-truth.json` / `questions.md` / `workload-*.txt` | Queries/traces |
| `corpus/` | Test corpus, if local |
| `artifacts.md` | External artifact manifest, if used |

## References

- [`protocol.md`](./protocol.md)
- <prior experiment>
- <ADR / OpenSpec change>
- <paper / documentation / issue>
