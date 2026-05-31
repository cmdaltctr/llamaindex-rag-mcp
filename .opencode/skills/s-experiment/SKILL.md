---
name: s-experiment
description: >
  Run empirical experiments for the RAG pipeline. Use when the user asks to
  plan, design, run, resume, or analyse an experiment in the experiments/ directory.
  Covers: creating experiment directories from protocol templates, writing run_eval.py
  runners and summarise_eval.py scripts, building indexes, running evaluations with
  checkpoint/resume, aggregating results, writing results.md, and updating EXP_README.md.
  Triggers: "run experiment", "plan experiment", "create experiment", "resume eval",
  "summarise results", "experiment protocol", "experiment 9b", "experiment N",
  "eval runner", "ground truth", "cell matrix".
---

# s-experiment: RAG Pipeline Experiment Runner

## Workflow

Every experiment follows 7 phases. Execute in order.

### Phase 1: Scope

Clarify before building:
- What decision depends on the result?
- Baseline vs candidate — what is the single variable under test?
- What corpus is available? Is it large enough to avoid saturation?
- What are the pass gates (win conditions + regression guards)?

### Phase 2: Create experiment directory

```bash
mkdir experiments/<N><slug>-<YYYY-MM-DD>
```

Copy the full protocol template from `references/protocol-template.md` into `protocol.md`.
Fill every section before running — ground truth and success criteria must be written first.

For lightweight/quick experiments, use the simpler template from `references/exp-template.md` as `results.md` scaffold.

### Phase 3: Write run_eval.py

See `references/eval-runner-pattern.md` for the canonical runner structure:
- Loads ground truth, iterates cells, calls `rag_mcp.retrieval.search`
- Saves atomic checkpoint (`eval_results_checkpoint.json`) per cell
- Supports `--resume` to skip completed cells
- Supports `--modes`, `--rerank-cross`, `--k-values`, `--limit-queries`

Key patterns:
- Use `sys.path.insert(0, str(PROJECT_ROOT / "src"))` to import from source
- Set env vars AND patch module-level globals to override config per cell
- Call `_cached_query_embedding.cache_clear()` between cells
- Write checkpoint atomically: write to `.tmp` then `Path.replace()`

### Phase 4: Build indexes / fixtures

```bash
# Use isolated experiment-local ChromaDB directories.
# Never touch production data.
CHROMA_PERSIST_DIR=./experiments/<id>/output/chroma_<mode> uv run python build_indexes.py
```

### Phase 5: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u experiments/<id>/run_eval.py \
  --modes <mode1>,<mode2> --rerank-cross --resume --k-values 5 10 20 50 \
  2>&1 | tee experiments/<id>/output/run_eval.log
```

If interrupted, re-run with `--resume` to pick up from the last checkpoint.

### Phase 6: Summarise

See `references/summarise-pattern.md` for the canonical summariser:
- Load `eval_results.json`, aggregate metrics per cell/category
- Compute pass gates and write recommendation
- Output `eval_results.summary.json` and `results.md`

```bash
uv run python experiments/<id>/summarise_eval.py
```

### Phase 7: Close out

1. Write `results.md` with executive summary, metrics tables, pass gates, recommendation
2. Update `protocol.md` status to PASS / FAIL / INCONCLUSIVE
3. Update `experiments/EXP_README.md` index table with the new entry
4. Add cross-reference if the experiment informs a code change

## Conventions

| Rule | Detail |
|------|--------|
| Naming | `<N><what-tested>-<YYYY-MM-DD>` (e.g. `9a-hybrid-retrieval-freshstack-2026-05-30`) |
| Isolation | `CHROMA_PERSIST_DIR=./output/chroma_<mode>` — never production data |
| Ground truth | Write queries and expected answers BEFORE running |
| Operator | Record who (or what agent) ran the experiment |
| Raw data | Always save JSON alongside Markdown summaries |
| Status | PLANNED → READY TO RUN → ACTIVE → PASS/FAIL/INCONCLUSIVE |
| Cleanup | Document removal of temp indexes; keep raw JSON and Markdown |

## References

- **Protocol template** (full): `references/protocol-template.md` — copy to `protocol.md`
- **Simple template**: `references/exp-template.md` — lightweight scaffold
- **Eval runner pattern**: `references/eval-runner-pattern.md` — canonical `run_eval.py`
- **Summariser pattern**: `references/summarise-pattern.md` — canonical `summarise_eval.py`
