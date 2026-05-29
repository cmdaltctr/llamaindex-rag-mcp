# Experiment 6b — Qasper Evidence-Level Markdown Chunking

This experiment repairs Experiment 6's evidence-sparsity problem. It evaluates
Markdown-aware chunking with evidence-level labels instead of source-file Hit@K.

HiCBench was originally considered because the HiChunk paper listed it as the
canonical benchmark, but the published Hugging Face URL was unavailable/404 at
run time and the paper was later withdrawn from ICLR 2026. Qasper is therefore
the canonical corpus for Experiment 6b.

## Qasper workflow

1. Prepare the normalised Qasper corpus and QA labels:

   ```bash
   uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/prepare_dataset.py \
     --source qasper \
     --qasper-split dev \
     --qasper-max-papers 20 \
     --qasper-max-queries 80
   ```

2. Ingest both indexes:

   ```bash
   EMBED_MODEL=qwen3-embedding:0.6b \
     uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/ingest_both.py
   ```

3. Run the evidence-level evaluator:

   ```bash
   EMBED_MODEL=qwen3-embedding:0.6b \
     uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py
   ```

## Synthetic fallback workflow

The synthetic fallback is intentionally opt-in and exists only to keep the
evaluation script exercised in CI / smoke tests. It is not a canonical 6b result.

```bash
uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/prepare_dataset.py \
  --allow-synthetic-fallback
```

Any result produced from the fallback corpus is fallback-only. `eval_results.json`
records `dataset_source` so fallback runs are clearly distinguishable from the
canonical Qasper run.
