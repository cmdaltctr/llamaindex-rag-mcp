# Experiment 7a — Chunk Overlap Sensitivity on Qasper

This is a self-contained follow-up to Experiment 7.

Experiment 7 used the small Exp 3 smoke corpus and saturated at source-level
Hit@1. Experiment 7a re-runs the overlap question on the Qasper-dev evidence
corpus used by Experiments 6b/6c, with evidence-level metrics.

## Self-contained artefacts

- `corpus/` — copied Qasper-dev Markdown corpus from Experiment 6b; no symlink.
- `ground-truth.json` — copied Qasper evidence labels from Experiment 6b; no symlink.
- `prepare_dataset.py` — copied Qasper adapter so the local corpus can be regenerated.
- `ingest_overlap.py` — builds one ChromaDB per overlap value.
- `run_eval.py` — evaluates overlap × pass × top_k using evidence-level metrics.
- `protocol.md` — hypothesis, method, criteria, and known-Qasper note.

## Run

```bash
cd experiments/7a-chunk-overlap-evidence-2026-05-29

uv run python ingest_overlap.py --overlaps 32,64,100,128

uv run python run_eval.py \
  --overlaps 32,64,100,128 \
  --top-ks 5,10,20 \
  --rerank both \
  --out eval_results.json
```

Pass A is `rerank=off`. Pass B is `rerank=on` with ADR-016's wider pool.

To regenerate the copied Qasper artefacts from scratch:

```bash
uv run python prepare_dataset.py --source qasper --qasper-split dev \
  --qasper-max-papers 20 --qasper-max-queries 80
```

## Intent

Keep production `CHUNK_OVERLAP=100`, but document Qasper as a known stress
case if the evidence-level result underperforms overlap 64.
