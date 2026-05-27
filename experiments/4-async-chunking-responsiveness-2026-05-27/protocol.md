# Experiment 4: Async Chunking Responsiveness Under Ingest Load

**ID**: `async-chunking-responsiveness-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-reliability-correctness-fixes` (Tier 1)

---

## What this experiment is for

The Tier 1 OpenSpec change wraps the chunk-splitting step inside ingestion with
`asyncio.to_thread`. The point is to keep the MCP event loop responsive while a
large file is being chunked, so concurrent `search_documents` calls do not stall
behind the synchronous splitter.

This experiment is the only honest way to confirm the change actually does what
it claims. Pure unit tests cannot detect event-loop blocking — you have to run
ingestion and search concurrently and measure search latency from the outside.

If the change works, search latency during ingest looks roughly the same as
search latency on an idle server. If the change does not work (or the splitter
is still secretly synchronous somewhere), search latency during ingest spikes
upward.

---

## Hypothesis

When `ingest_path_async` is processing a large document, concurrent
`search_documents` calls remain responsive: the post-fix **P95 search latency
during ingest is at most 2× the P95 measured on an idle server**.

The 2× ceiling is generous on purpose. We expect the post-fix P95 to land
much closer to 1.0×–1.2× of idle, but a thread-offloaded chunker can still
share CPU with the embed worker pool, so a small uplift is acceptable.

---

## Background

The async ingestion path in `src/rag_mcp/ingestion.py` already offloads file
reading and ChromaDB writes to threads. Chunk splitting via
`SentenceSplitter.get_nodes_from_documents(...)` is the last remaining
synchronous step. On a 200-page PDF or a 5 MB Markdown file, splitting can
run for several seconds inside the event-loop coroutine, blocking everything
else queued on it — including incoming MCP requests.

The fix is to wrap the call in `asyncio.to_thread(...)` so the splitter runs
on a worker thread. This experiment proves the fix landed correctly.

The pattern is documented in
`openspec/changes/rag-reliability-correctness-fixes/design.md` (Decision 1).

---

## Variables

| Type        | Variable                                             | Values                                                |
| ----------- | ---------------------------------------------------- | ----------------------------------------------------- |
| Independent | Code under test                                      | `pre-fix` (sync splitter), `post-fix` (`to_thread`)   |
| Dependent   | Search P50 / P95 latency during ingest (ms)          | —                                                     |
| Dependent   | Search P50 / P95 latency on idle server (ms)         | —                                                     |
| Dependent   | Ingest wall-clock time (s)                           | —                                                     |
| Controlled  | Embedding model                                      | `qwen3-embedding:0.6b`                                |
| Controlled  | `EMBED_BATCH_SIZE`                                   | 100                                                   |
| Controlled  | `EMBED_CONCURRENCY`                                  | 2                                                     |
| Controlled  | `CHUNK_SIZE` / `CHUNK_OVERLAP`                       | 512 / 64                                              |
| Controlled  | Reranker                                             | Disabled (we want to measure the search cold path)    |
| Controlled  | Query cadence                                        | 1 query every 100 ms                                  |
| Controlled  | Total queries per run                                | 100                                                   |
| Controlled  | Hardware                                             | Apple Silicon Mac, 16 GB                              |

---

## Environment & Prerequisites

| Requirement   | Version / Value                                  |
| ------------- | ------------------------------------------------ |
| Python        | 3.12                                             |
| Ollama models | `qwen3-embedding:0.6b`                           |
| Hardware      | Apple Silicon Mac, 16 GB                         |
| Reranker      | Not used                                         |
| Pre-fix code  | Git tag or branch BEFORE Tier 1 lands            |
| Post-fix code | Git tag or branch AFTER Tier 1 task 1.2 is done  |

```bash
# Verify prerequisites
ollama list   # qwen3-embedding:0.6b must be present
uv sync
```

---

## Step 1: Prepare the corpus

The corpus is **one big file**. We deliberately want a chunk-heavy file so the
splitter spends real wall-clock time inside `get_nodes_from_documents`.

Place a single large document into the corpus directory:

```
experiments/4-async-chunking-responsiveness-2026-05-27/corpus/
└── large-document.pdf   (≥ 5 MB, expected to chunk into 1500+ chunks)
```

Acceptable substitutes if you don't have a 5 MB PDF handy:

| Option | Source                                                                        |
| ------ | ----------------------------------------------------------------------------- |
| 1      | A long technical PDF (≥ 200 pages)                                            |
| 2      | A long Markdown export of a docs site (≥ 5 MB)                                |
| 3      | Concatenate 20× a smaller PDF into one file using `pdftk` or similar          |
| 4      | Reuse `experiments/2-embedding-model-comparison-2026-05-19/corpus/*.pdf` if any single file is large enough |

**Why one big file**: the splitter's blocking time per file is what we are
testing. Many small files trigger the embed/write loop, not the splitter.

You can also use a smaller file if the post-fix P95 is genuinely better than
2× idle; the experiment just becomes weaker as a stress test.

---

## Step 2: Capture an idle-server baseline

Before any ingest runs, measure how fast `search_documents` responds when the
server is doing nothing else. This is the reference number.

```bash
# Start the MCP server in stdio mode pointing at a fresh ChromaDB.
# Pre-populate it with a small fixture so search has something to retrieve.
CHROMA_PERSIST_DIR=./chroma_db_test \
  uv run rag-mcp ingest tests/fixtures/sample.txt

# Run the harness in idle-baseline mode.
CHROMA_PERSIST_DIR=./chroma_db_test \
  uv run python experiments/4-async-chunking-responsiveness-2026-05-27/run_eval.py \
  --mode idle-baseline \
  --queries 100 \
  --cadence-ms 100 \
  --output idle-baseline.json
```

The harness fires 100 queries at 100 ms cadence and records latency for each
one. Save the output as `idle-baseline.json`. Repeat 3 times and use the median
P50 / P95 across runs to absorb warm-up noise.

---

## Step 3: Run the under-load measurement

This is the actual test. We start an ingest of the large file and, as soon as
chunking begins, start firing the same 100 queries at the same 100 ms cadence.

**Repetition for statistical significance**: each treatment (pre-fix and
post-fix) is run **3 times** under load, matching the 3 idle-baseline runs.
The reported P95 for each treatment is the **median P95 across its 3 runs**;
this is robust to the long tail that a single noisy run can produce when the
embed worker pool contends for cores. The same numbering scheme applies to
ingest wall-clock — report the median.

```bash
# Post-fix runs (from the feature branch checkout):
for i in 1 2 3; do
  CHROMA_PERSIST_DIR=./chroma_db_test \
    uv run python experiments/4-async-chunking-responsiveness-2026-05-27/run_eval.py \
    --mode under-load \
    --ingest-path experiments/4-async-chunking-responsiveness-2026-05-27/corpus \
    --queries 100 --cadence-ms 100 \
    --output under-load-postfix-${i}.json
done
```

The harness:

1. Spawns a coroutine that calls `ingest_path_async("corpus")`.
2. As soon as ingestion has started, spawns a second coroutine that fires
   100 search queries at 100 ms cadence.
3. Records per-query latency, per-query timestamp, and the ingest wall-clock.
4. Writes the full timeline to `under-load-postfix-${i}.json`.

### Pre-fix control via git worktree

The post-fix code path includes the `asyncio.to_thread` wrap around the
splitter. To capture pre-fix behaviour without thrashing the working branch,
use a `git worktree` checked out at `master` (or the last commit before the
splitter offload landed):

```bash
# Create the pre-fix worktree as a sibling directory.
git worktree add ../llamaindex-rag-mcp-prefix master

# Copy the experiment harness + corpus into the worktree (master doesn't
# carry the experiment directory yet).
cp -r experiments/4-async-chunking-responsiveness-2026-05-27 \
      ../llamaindex-rag-mcp-prefix/experiments/

# Sync deps inside the worktree (independent .venv).
cd ../llamaindex-rag-mcp-prefix
uv sync

# Seed the fixture so search() has a chunk to retrieve.
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp ingest tests/fixtures/sample.txt

# Pre-fix runs (3 repetitions matching post-fix).
for i in 1 2 3; do
  CHROMA_PERSIST_DIR=./chroma_db_test \
    uv run python experiments/4-async-chunking-responsiveness-2026-05-27/run_eval.py \
    --mode under-load \
    --ingest-path experiments/4-async-chunking-responsiveness-2026-05-27/corpus \
    --queries 100 --cadence-ms 100 \
    --output under-load-prefix-${i}.json
done

# Move the JSON outputs back to the feature branch for the comparison report.
cp experiments/4-async-chunking-responsiveness-2026-05-27/under-load-prefix-*.json \
   /path/to/feature-branch/experiments/4-async-chunking-responsiveness-2026-05-27/
cd -

# When done, prune the worktree.
git worktree remove ../llamaindex-rag-mcp-prefix
```

Why a worktree rather than `git stash` or branch-switching: a worktree gets
its own checkout, its own `.venv`, and its own ChromaDB persist dir, so the
pre-fix and post-fix harnesses can run without contaminating each other or
forcing a deps-reinstall round-trip.

If you cannot run the worktree path (e.g. a different machine or the corpus
won't fit on disk twice), run only the post-fix path 3 times and treat the
idle baseline as the "what good looks like" reference — but the pre-fix
sanity and ingest-throughput checks then drop to *unverified* in the
results table, not *passed*.

---

## Step 4: Compute and compare

The harness prints a comparison table at the end:

```
┌──────────────────────┬────────┬────────┬────────┬───────────┐
│ Run                  │ P50 ms │ P95 ms │ P99 ms │ Ingest s  │
├──────────────────────┼────────┼────────┼────────┼───────────┤
│ idle-baseline        │   30.1 │   42.7 │   58.0 │       —   │
│ under-load (pre-fix) │  120.3 │ 1850.2 │ 2310.4 │      48.6 │
│ under-load (post-fix)│   34.5 │   55.1 │   71.2 │      50.1 │
└──────────────────────┴────────┴────────┴────────┴───────────┘
```

Save the table inline in `results.md` and the raw JSON files as artefacts.

---

## Success Criteria

| Check                                                 | Pass condition                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Post-fix search responsiveness                        | `under-load (post-fix)` P95 ≤ 2× `idle-baseline` P95                                        |
| Pre-fix search responsiveness (sanity)                | `under-load (pre-fix)` P95 > 2× `idle-baseline` P95 (confirms the bug exists pre-fix)       |
| Ingest throughput unaffected                          | `under-load (post-fix)` ingest wall-clock ≤ 1.05× `under-load (pre-fix)` ingest wall-clock  |
| Zero ingest errors                                    | Ingest reports `status: "ok"`                                                               |
| Zero search errors                                    | All 100 search calls return a list (success or error envelope), none raise                  |

If post-fix P95 > 2× idle P95, the offload is incomplete. Possible causes:
- Splitter still called outside `to_thread` somewhere
- Embed worker pool starving the event loop independently
- Disk I/O dominating (re-run with the corpus cached in OS page cache)

If post-fix ingest wall-clock regresses by more than 5 %, the thread-offload
overhead is too high for the file size — revisit thread pool sizing.

---

## What to do if the experiment fails

This experiment is part of the loop on Tier 1. If P95 exceeds 2× idle:

1. Re-read `openspec/changes/rag-reliability-correctness-fixes/tasks.md`
   tasks 1.1 / 1.2.
2. Add explicit `await asyncio.sleep(0)` after the splitter call to surrender
   the event loop, or wrap embed-worker dispatch in `to_thread` too.
3. Re-run the experiment.
4. Loop until criteria pass, then re-validate Tier 1's pytest suite with
   `uv run pytest -m "not slow" --cov=rag_mcp`.

---

## Cleanup

```bash
rm -rf ./chroma_db_test
```

---

## References

- `openspec/changes/rag-reliability-correctness-fixes/design.md` — Decision 1
- `openspec/changes/rag-reliability-correctness-fixes/tasks.md` — tasks 1.1–1.4
- AGENTS.md (project root) — "All ingestion is async" rule
- Python docs: `asyncio.to_thread` — https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread

---

## Artefacts

| File                       | Description                                                       |
| -------------------------- | ----------------------------------------------------------------- |
| `protocol.md`              | This file — hypothesis, method, reproduction steps                |
| `run_eval.py`              | Automation harness (idle-baseline + under-load modes)             |
| `idle-baseline.json`       | Raw per-query latencies for the idle baseline run                 |
| `under-load-prefix.json`   | Raw per-query latencies for the under-load run on pre-fix code   |
| `under-load-postfix.json`  | Raw per-query latencies for the under-load run on post-fix code  |
| `results.md`               | Comparison table and conclusion                                   |
| `corpus/`                  | The single large document used as the ingest payload              |
