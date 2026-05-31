# Experiment <N>: <Descriptive Title>

**ID**: `<experiment-directory-name>`  
**Date planned**: YYYY-MM-DD  
**Operator**: <human operator> with <AI/build agent, if used>  
**Status**: PLANNED | READY TO RUN | ACTIVE  
**Relation**: <OpenSpec change / ADR / prior experiment / issue, if any>

---

## Why this experiment exists

State the concrete problem, uncertainty, or decision this experiment is meant
to resolve. Prefer one or two paragraphs.

Good prompts:

- What previous result, bug, ADR, or OpenSpec task forced this experiment?
- What production default, implementation path, or follow-up change depends on
  the answer?
- Is this a first-pass experiment, a follow-up, or a validation of an existing
  implementation?

## Hypothesis / Research question

Write the falsifiable claim before running the experiment.

Example:

> With `<change>`, `<metric>` improves by at least `<threshold>` against
> `<baseline>` while `<guardrail metric>` does not regress beyond `<tolerance>`.

If there are multiple hypotheses, number them:

1. <Primary hypothesis>
2. <Secondary hypothesis / negative control>
3. <Production-shaped hypothesis, if different from isolation test>

## Background and prior evidence

Summarise only the evidence needed to understand the design.

- Prior experiments: `<path/to/results.md>`
- ADRs / OpenSpec changes: `<path>`
- Relevant code paths: `<module.function>`
- External papers / docs: `<citation or URL>`

Record known caveats here, especially corpus saturation, prior negative
results, known stress cases, or implementation constraints.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | <thing changed> | <baseline, candidate, sweep values> |
| Independent | <optional second factor> | <values> |
| Dependent | <primary metric> | <Hit@1, Evidence Recall@5, latency, etc.> |
| Dependent | <diagnostic metric> | <MRR, nDCG, P95, chunk count, embed calls, etc.> |
| Controlled | Corpus | <fixed corpus / source> |
| Controlled | Model / config | <embedding model, reranker, chunk size, top_k, etc.> |

State explicitly what is **not** being changed. This prevents accidental
multi-variable experiments.

## Corpus and ground truth

Describe the data before running the experiment.

| Item | Value |
| --- | --- |
| Source | <dataset, copied experiment, generated fixtures, production sample, etc.> |
| Local path | `experiments/<id>/corpus/` |
| Size | <documents, chunks, QA records, calls, etc.> |
| Ground truth path | `experiments/<id>/ground-truth.json` or `<queries/workload file>` |
| Evidence density | <% with evidence / expected answer, if applicable> |
| Symlinks? | No symlinks preferred; explain if unavoidable |

If the corpus is copied from another experiment, say whether indexes are also
copied or rebuilt. Rebuild when stored file paths would otherwise point to the
old experiment directory.

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Embedding model | `<model>` |
| Reranker / LLM | `<model or disabled>` |
| Hardware | <machine class, RAM, accelerator> |
| Key config | `<ENV=value>`, `<ENV=value>` |

```bash
# Sanity checks before running
uv sync
ollama list
```

## Experimental design / cell matrix

Use this section for sweeps, phases, Pass A/Pass B designs, cache-on/off cells,
baseline/candidate comparisons, or negative controls.

| Run ID | Purpose | Baseline / candidate | Key settings | Expected interpretation |
| --- | --- | --- | --- | --- |
| `1A-example` | <isolation pass> | <baseline vs candidate> | `<setting=value>` | <what this cell proves> |
| `1B-example` | <production-shaped pass> | <baseline vs candidate> | `<setting=value>` | <what this cell proves> |

If using phases, include stop rules:

- Phase 1 stop rule: <condition>
- Phase 2 stop rule: <condition>
- Escalation rule: <when to propose bigger implementation work>

## Metrics

Primary metrics are gated. Diagnostic metrics explain the result but do not
decide pass/fail unless listed under success criteria.

### Primary metrics

- <Metric 1>: <definition, K value, numerator/denominator>
- <Metric 2>: <definition>

### Diagnostic metrics

- <Metric>: <why it matters>
- <Metric>: <why it matters>

For retrieval experiments, prefer recording both quality and operational shape:

- Hit@K / Evidence Recall@K / MRR / nDCG
- source-document hit rate vs evidence-level hit rate
- chunk count, mean/P95/max token estimate
- mean/P95 latency
- cache hit rate / embed-call count, if applicable

## Procedure / reproduction commands

Commands should be copy-pasteable from the repository root unless this section
explicitly changes directory.

### Step 1: Prepare data

```bash
# Copy or generate corpus and ground truth
<command>
```

### Step 2: Build indexes / fixtures

```bash
# Use isolated experiment-local or temp ChromaDB directories.
# Never touch production data.
<command>
```

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/<id>/run_eval.py \
  --modes <mode1>,<mode2> \
  --rerank-cross \
  --resume \
  --k-values 5 10 20 50
```

The runner saves raw per-query results, parent-ID mappings, latency,
and fusion diagnostics to `eval_results.json`.

**Checkpoint and resume**: The runner saves an atomic checkpoint to
`eval_results_checkpoint.json` after each completed cell (mode × rerank combination).
Use `--resume` to load the checkpoint and skip already-completed cells if the
experiment is interrupted. The checkpoint is written atomically (write to `.tmp`
then rename) to prevent corruption. This allows the experiment to be safely
resumed without losing progress from earlier cells.

### Step 4: Summarise raw results

```bash
<command to aggregate raw JSON into summary JSON/table, if any>
```

## Success criteria / pass gates

Write these before running. Include both win conditions and regression guards.

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| <primary metric lift> | `<candidate - baseline >= X>` | <production decision it supports> |
| <non-regression guard> | `<candidate >= baseline - Y>` | <risk controlled> |
| <latency/resource guard> | `<P95 <= ...>` | <operational constraint> |
| <data-quality guard> | `<evidence density >= ...>` | <validity constraint> |

If criteria differ by pass/cell, spell that out here.

## Interpretation rules

Pre-commit to what each outcome means.

- If the primary gate passes: <decision / default promotion / implementation>
- If only production-shaped pass succeeds: <decision and caveat>
- If isolation pass fails but guardrails pass: <decision and caveat>
- If the corpus saturates: <whether to mark PARTIAL/INCONCLUSIVE and what harder
  benchmark is needed>
- If the result is negative: <what will not ship, and what follow-up is allowed>

## What to do if the experiment fails

Avoid improvising after seeing results. List planned fallbacks in priority order.

1. <First fallback, usually document negative result / keep current default>
2. <Second fallback, e.g. harder corpus or specific implementation alternative>
3. <Escalation path, e.g. new OpenSpec change>

## Implementation notes

Record important code-path assumptions and safety constraints.

- Code path under test: `<module.function>`
- Flags/env vars used: `<ENV=value>`
- Monkey patches or test-only hooks: <none / description>
- Scope boundaries: <e.g. Markdown branch only; reranker unchanged>
- Known risks: <e.g. cache leakage, path drift, baseline saturation>

## Cleanup

```bash
# Remove temporary indexes, generated traces, or one-off artifacts if desired
<cleanup command>
```

State whether raw data should be kept. Usually keep raw JSON and Markdown
summaries; remove only large generated indexes if they are reproducible.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable result report | ✅ |
| `run_eval.py` | Evaluation runner | Usually |
| `eval_results.json` or `eval_results.*.json` | Raw machine-readable results | ✅ |
| `eval_results_checkpoint.json` | Cell-by-cell checkpoint for resume | Usually |
| `eval_results.summary.json` | Aggregated summary, if raw data is large | Optional |
| `output/*.log` | Run logs | Optional |
| `ground-truth.json` / `questions.md` / `workload-*.txt` | Pre-written queries or traces | Usually |
| `corpus/` | Local test documents | Usually |
| `artifacts.md` | Pointer to external artifacts, if too large for git | Optional |

## References

- <Prior experiment result/protocol>
- <ADR / OpenSpec change>
- <Paper / documentation / issue>
