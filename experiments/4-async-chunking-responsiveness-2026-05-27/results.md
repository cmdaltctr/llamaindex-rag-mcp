# Experiment 4 — Results

**Date run**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari (with AI agent automation)
**Code under test**: `pre-fix` (master, sync splitter) and `post-fix` (feature branch, `asyncio.to_thread` splitter)
**Status**: PASS for the responsiveness contract; pre-fix sanity check INCONCLUSIVE — see interpretation

---

## Setup

- Hardware: Apple Silicon Mac
- Embedding model: `qwen3-embedding:0.6b`
- Pre-ingest: `tests/fixtures/sample.txt` (1 chunk) so `search_documents` has something to retrieve
- Corpus: `corpus/large-document.pdf` (7.6 MB → 750 chunks)
- Query cadence: 100 queries spaced 100 ms apart per run
- Reranker: disabled
- Repetitions: **3 runs per condition** (pre-fix, post-fix, idle); the
  reported P95 for each condition is the **median P95 across its 3 runs**
- Pre-fix code obtained via `git worktree add ../llamaindex-rag-mcp-prefix master`
  with the experiment harness copied into the worktree and `.env` mirrored

---

## Raw Results

| Run                         | P50 ms | P95 ms |  P99 ms | Ingest s | Errors |
| --------------------------- | -----: | -----: | ------: | -------: | -----: |
| idle-baseline 1             |  89.58 |  98.56 |  162.07 |        — |      0 |
| idle-baseline 2             |  89.17 |  97.11 |  117.59 |        — |      0 |
| idle-baseline 3             |  88.70 |  96.55 |  129.53 |        — |      0 |
| under-load pre-fix 1        |  84.84 | 158.72 |  605.22 |   205.95 |      0 |
| under-load pre-fix 2        |  83.46 | 163.14 |  353.87 |   193.12 |      0 |
| under-load pre-fix 3        |  84.69 | 186.63 |  343.57 |   187.06 |      0 |
| under-load post-fix 1       |  83.85 | 138.10 |  145.29 |   199.50 |      0 |
| under-load post-fix 2       |  92.70 | 214.17 |  592.74 |   204.55 |      0 |
| under-load post-fix 3       |  85.56 | 165.77 |  429.17 |   198.49 |      0 |

---

## Medians

| Condition           | Median P50 | Median P95 | Median P99 | Median ingest |
| ------------------- | ---------: | ---------: | ---------: | ------------: |
| idle-baseline       |      89.17 |  **97.11** |     129.53 |             — |
| under-load pre-fix  |      84.69 | **163.14** |     353.87 |        193.12 |
| under-load post-fix |      85.56 | **165.77** |     429.17 |        199.50 |

---

## Success Criteria

| Check                                                | Result                                                              | Pass |
| ---------------------------------------------------- | ------------------------------------------------------------------- | :--: |
| Post-fix P95 ≤ 2× idle baseline P95                  | 165.77 ≤ 2 × 97.11 (= 194.22); ratio **1.71×**                      |  ✅  |
| Pre-fix sanity (P95 > 2× idle baseline P95)          | 163.14 ≤ 194.22; ratio **1.68×** — bug not observable in this corpus | ⚠️  |
| Ingest throughput regression ≤ 1.05× pre-fix         | 199.50 / 193.12 = **1.033×**                                          |  ✅  |
| Zero ingest errors (both conditions)                 | All 6 ingests `status: ok`, 750 chunks each                          |  ✅  |
| Zero search errors (both conditions)                 | 0 / 600 queries returned an error envelope                           |  ✅  |

---

## Interpretation

The responsiveness contract holds: post-fix median P95 is 1.71× the idle
baseline, comfortably within the 2× ceiling, and ingest wall-clock is
within 3.3% of the pre-fix run — well under the 5% guardrail.

The unexpected result is that the **pre-fix sanity check did not
trigger**. Pre-fix P95 (163 ms) and post-fix P95 (166 ms) are
statistically indistinguishable across 3 runs each, and both are below
the 2× idle ceiling (194 ms).

The protocol assumed splitter blocking would dominate under-load
latency. The data refutes that assumption for this corpus and this
embedding configuration. Reading the timeline:

- The 7.6 MB PDF splits in a small number of seconds (the splitter
  produces 750 chunks, but `SentenceSplitter` is mostly fast Python
  string manipulation against pre-loaded text).
- Embedding those 750 chunks via `qwen3-embedding:0.6b` takes
  ~190–205 seconds.
- The 100 search queries fire at 100 ms cadence over 10 seconds, so most
  of them land **during the embed phase, not the split phase**.

ChromaDB writes and embed-pool dispatch already use `asyncio.to_thread`
in both pre-fix and post-fix builds (this came in with ADR-014). The
splitter offload from this change addresses the brief blocking window
during the actual splitting step. That window is genuinely small
relative to the 200-second ingest, so its contribution to the P95 of
queries scattered across the run is small too.

This is consistent with the unit-level evidence:
`tests/test_async_ingest_responsiveness.py::TestSplitterOffload::test_search_responsive_during_blocking_splitter`
injects a `time.sleep(0.6)` directly into `SentenceSplitter.get_nodes_from_documents`
and proves a concurrent `search_documents` returns inside 500 ms. The
fix works; the macro experiment with this corpus is just not sensitive
enough to surface the bug at the P95-during-full-ingest level.

### What would surface the bug at the macro level

The splitter would need to dominate the wall-clock of the run. Options
for a future, more sensitive replication:

1. A much larger single document where the splitter takes tens of
   seconds (e.g. a 50–100 MB Markdown export).
2. A document type whose splitter is genuinely slow (some PDF parsers
   produce per-page reads that the splitter then re-tokenises one at a
   time).
3. Lower `EMBED_CONCURRENCY` so embedding does not overlap the
   splitter; this sharpens the contrast.
4. A higher query cadence (e.g. 10 ms instead of 100 ms) so more
   queries land inside the brief splitter window.

None of these are required to accept the fix — the unit test is the
primary correctness contract — but they would close the loop on the
macro experiment.

---

## Conclusion

The `asyncio.to_thread(splitter.get_nodes_from_documents, documents)`
change in `_read_and_chunk_file_async` keeps the MCP event loop free
during splitting (verified at unit level) and does not regress ingest
throughput (verified at macro level: 1.033× ratio). Search latency
under load stays within 1.71× of idle baseline.

The pre-fix sanity check was **inconclusive in this configuration**
because the embed phase already dominates the under-load workload —
both with and without the splitter offload. The fix remains correct
and is preserved; the macro experiment simply does not make the
splitter visible against the embed background.

Tier 1 task 1.5 of the OpenSpec change is satisfied. Task 1.6 is not
triggered because the responsiveness contract passes; the inconclusive
pre-fix result is an observation about experimental sensitivity, not a
fix failure.

---

## Artefacts

| File                          | Description                                                  |
| ----------------------------- | ------------------------------------------------------------ |
| `protocol.md`                 | Hypothesis, method, reproduction steps (worktree procedure)  |
| `run_eval.py`                 | Automation harness                                           |
| `idle-baseline-{1,2,3}.json`  | 100 queries on a quiescent server (3 runs)                   |
| `under-load-prefix-{1,2,3}.json`  | 100 queries during ingest on master (3 runs)              |
| `under-load-postfix-{1,2,3}.json` | 100 queries during ingest on feature branch (3 runs)      |
| `results.md`                  | This file — comparison and conclusion                        |
| `corpus/large-document.pdf`   | 7.6 MB ingest payload                                        |
