# Experiment 6c — Quick-Win Interventions for Markdown Chunking on Qasper

Follow-up to Experiment 6b's negative result. Same Qasper-dev corpus and same Pass A / Pass B methodology; tests four small-bore interventions that the literature and 6b's per-query drill agree on. Each intervention is independently cheap; the combined effect is the experiment's primary research question.

See `protocol.md` for the full methodology, run plan, and pass criteria.
See `../6b-qasper-markdown-chunking-2026-05-28/results.md` for the result this experiment is responding to.
See `openspec/changes/4-experiment-6c-markdown-chunking-quickwins/` for the OpenSpec change tracking 6c's work.

---

## Interventions at a glance

| ID | Intervention | Lines of code | Failure mode addressed |
| -- | ------------ | ------------: | ---------------------- |
| K  | `top_k` sweep at `{5, 10, 20}` | 0 (eval flag only) | Chunk crowding at fixed `top_k` |
| C  | Markdown-only `chunk_size ∈ {512, 768, 1024}` | ~3 | Smaller chunks lose embedder context |
| H  | Heading content prepend before embedding | ~10 | Keyword surface area, heading routing signal |
| F  | Min-chunk-size floor at `chunk_size * 0.5` | ~15 | Orienting `## Introduction` chunks displace evidence |
| M  | Defensive `header_path` copy after `_split_sync()` | ~8 | Test-coverage gap; Section Match@1 belt-and-braces |

The two larger changes deferred to a future OpenSpec change (only if 6c's small-bore interventions are insufficient):

- `HierarchicalNodeParser([1024, 512])` + `AutoMergingRetriever`
- Anthropic-style contextual retrieval via local Ollama `qwen3:0.6b`

---

## Workflow

1. Reuse 6b's corpus and ground truth by **copying** them into 6c — do NOT symlink. 6c is self-contained:

   ```bash
   cp -R experiments/6b-qasper-markdown-chunking-2026-05-28/corpus \
         experiments/6c-markdown-chunking-quickwins-2026-05-28/corpus
   cp experiments/6b-qasper-markdown-chunking-2026-05-28/ground-truth.json \
         experiments/6c-markdown-chunking-quickwins-2026-05-28/ground-truth.json
   cp -R experiments/6b-qasper-markdown-chunking-2026-05-28/chroma_baseline \
         experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_baseline
   ```

2. Phase 1 — `top_k` sweep on the copied 6b candidate ChromaDB (no rebuild):

   ```bash
   mkdir -p experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_candidate_runs
   cp -R experiments/6b-qasper-markdown-chunking-2026-05-28/chroma_candidate \
         experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_candidate_runs/baseline_6b

   for k in 5 10 20; do
     EMBED_MODEL=qwen3-embedding:0.6b \
       uv run python experiments/6c-markdown-chunking-quickwins-2026-05-28/run_eval.py \
         --pass-name A --rerank off --top-k $k \
         --candidate-dir experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_candidate_runs/baseline_6b \
         --output experiments/6c-markdown-chunking-quickwins-2026-05-28/eval_results.1A-k$k.json
   done

   # Repeat the loop with --pass-name B --rerank on for Pass B.
   ```

3. Phase 2 — `chunk_size` sweep on the Markdown branch only. Build a new candidate ChromaDB per `chunk_size`:

   ```bash
   for size in 768 1024; do
     EMBED_MODEL=qwen3-embedding:0.6b \
       uv run python experiments/6c-markdown-chunking-quickwins-2026-05-28/ingest_candidate.py \
         --chunk-size $size \
         --out-dir experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_candidate_runs/c$size
   done
   ```

4. Phases 3 and 4 — heading prepend (H), min-size floor (F), defensive metadata copy (M). Rebuild candidates with the appropriate `--heading-prepend / --min-size-floor / --metadata-copy` flags. See `protocol.md` for the full matrix.

---

## Stop rules

- If `1A-k10` (Pass A, `top_k=10`, no chunker change) lands at parity-or-better with the baseline AND `1B-k10` is non-negative on Evidence Recall@5, the production answer is "ship the Markdown chunker as-is and recommend `top_k ≥ 10`". Phases 2–4 still run for completeness but the deployment recommendation is settled.
- If Phases 1–4 all leave the verdict negative, escalate to the deferred big-swing OpenSpec change (HierarchicalNodeParser + AutoMergingRetriever, or contextual retrieval).

---

## Artefacts

- `protocol.md` — full methodology, run plan, pass criteria.
- `ingest_candidate.py` — parameterised ingestion (to be implemented during build phase). Accepts `--chunk-size`, `--heading-prepend`, `--min-size-floor`, `--metadata-copy`, `--out-dir`.
- `run_eval.py` — forked from 6b's evaluator. Adds `--top-k INT` and `--candidate-dir PATH` flags; otherwise identical.
- `eval_results.<run-id>.json` — one per cell of the run matrix.
- `chroma_candidate_runs/<run-id>/` — per-run candidate ChromaDB persist directories. The 6b candidate is symlinked in as `baseline_6b/` for Phase 1.
- `results.md` — written after the matrix is run. One TL;DR table, per-phase tables, the production recommendation, and the per-query failure-mode replication of 6b's drill.

---

## Why this experiment over the bigger swings

The 6b post-mortem identified four contributing causes for the −5.66 pp regression. The dominant cause is chunk fragmentation at fixed `top_k`, which the reranker (Pass B) already partially fixes by fetching 50 candidates. That tells us the gold-evidence chunks exist in the index — they're just at ranks 6–15. The cheapest possible fix is therefore a `top_k` change, which 6c tests in 0 LOC. The next-cheapest is a `chunk_size` bump on the Markdown branch only, which is 3 LOC. The interventions in 6c are ordered cheapest-first because each one is a clean reading on a specific cause, and the combined matrix is small enough to run in one afternoon.

The deferred big-swings would each require a separate OpenSpec change touching `retrieval.py`'s search shape (auto-merging) or adding minutes of ingestion latency (contextual retrieval). Those are right answers in principle but disproportionate effort if the small-bore interventions carry us. We commit to running 6c first and only escalating if it fails its parity threshold.
