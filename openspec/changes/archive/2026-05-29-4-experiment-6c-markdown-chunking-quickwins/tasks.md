# Implementation Tasks — Experiment 6c: Markdown Chunking Quick-Wins

This change is **experiment-scoped**. It adds knobs and a run scaffold; it does NOT change production defaults. Defaults move in a follow-up `5-experiment-6c-promote-defaults` change after 6c's `results.md` is written.

Phases 1–2 below were executed in `experiments/6c-markdown-chunking-quickwins-2026-05-28/`. Phases 3–4 remain deferred because Phase 2 already found a production-shape winning configuration (`MARKDOWN_CHUNK_SIZE=1024` with reranker enabled).

---

## Cross-experiment audit

- [x] Confirm Experiment 6 exists and records the saturated 5-document Markdown result: `experiments/6-markdown-chunking-quality-2026-05-27/results.md`
- [x] Confirm Experiment 6b exists and records the Qasper negative result at `chunk_size=512`, `top_k=5`: `experiments/6b-qasper-markdown-chunking-2026-05-28/results.md`
- [x] Confirm Experiment 6c exists, is self-contained, and records the quick-win result: `experiments/6c-markdown-chunking-quickwins-2026-05-28/results.md`
- [x] Confirm 6c has no runtime dependency on 6b symlinks; its `corpus/`, `ground-truth.json`, baseline index, and candidate indexes live under the 6c directory

---

## Phase 0 — Scaffold and configuration knobs

### 0.1 Experiment directory scaffold

- [x] Create `experiments/6c-markdown-chunking-quickwins-2026-05-28/`
- [x] Write `protocol.md` — full methodology, run matrix, pass criteria
- [x] Write `README.md` — workflow, stop rules, deferred big-swings
- [x] Copy corpus and ground truth into 6c so the experiment is self-contained (no symlinks), then rebuild the baseline and candidate indexes from the 6c-local corpus so ChromaDB metadata paths point at `experiments/6c.../corpus/`:
  ```bash
  cp -R experiments/6b-qasper-markdown-chunking-2026-05-28/corpus \
        experiments/6c-markdown-chunking-quickwins-2026-05-28/corpus
  cp experiments/6b-qasper-markdown-chunking-2026-05-28/ground-truth.json \
        experiments/6c-markdown-chunking-quickwins-2026-05-28/ground-truth.json
  EMBED_MODEL=qwen3-embedding:0.6b \
    uv run python experiments/6c-markdown-chunking-quickwins-2026-05-28/ingest_baseline.py
  EMBED_MODEL=qwen3-embedding:0.6b \
    uv run python experiments/6c-markdown-chunking-quickwins-2026-05-28/ingest_candidate.py \
      --chunk-size 512 \
      --out-dir experiments/6c-markdown-chunking-quickwins-2026-05-28/chroma_candidate_runs/baseline_6b
  ```
- [x] Add `ingest_baseline.py` so 6c can rebuild the baseline index locally rather than copying stale 6b ChromaDB metadata

### 0.2 Configuration knobs in `src/rag_mcp/config.py`

All three default to "no behaviour change":

- [x] Add `MARKDOWN_CHUNK_SIZE: int = int(os.environ.get("MARKDOWN_CHUNK_SIZE", str(CHUNK_SIZE)))`
- [x] Add `MARKDOWN_HEADING_PREPEND: bool = os.environ.get("MARKDOWN_HEADING_PREPEND", "false").lower() == "true"`
- [x] Add `MARKDOWN_MIN_CHUNK_FRACTION: float = float(os.environ.get("MARKDOWN_MIN_CHUNK_FRACTION", "0.0"))`
- [x] Document all three in `.env.example` with experimental-status comment
- [x] Verify `import config` does not change semantics for callers that don't set the new vars (regression test: existing tests pass unchanged)

### 0.3 Defensive heading metadata helper

- [x] In `rag_mcp/ingestion.py`, add module-private `_ensure_heading_metadata(nodes: list) -> None` that defensively copies `header_path` / `heading_path` from `source_node.metadata` when present
- [x] Always call `_ensure_heading_metadata(nodes)` after `_split_sync()` in the `is_markdown` branch — this is the M intervention, always-on because it is idempotent and fixes a real test gap

### 0.4 Heading-prepend hook

- [x] In `rag_mcp/ingestion.py`, add `_apply_heading_prepend(nodes: list) -> None` that iterates emitted nodes and prepends `[<header_path>] ` to `node.text` when `MARKDOWN_HEADING_PREPEND` is true and `header_path` is non-empty
- [x] Guard: skip prepend when the exact prefix already appears at the start of `node.text` (prevents double-prepend on re-ingestion)
- [x] Call hook after `_ensure_heading_metadata` and before metadata-extractor merge

### 0.5 Min-size-floor hook

- [x] In `rag_mcp/ingestion.py`, add `_drop_small_markdown_chunks(nodes: list, chunk_size: int) -> list` that returns nodes filtered by `len(node.text) >= chunk_size * 4 * MARKDOWN_MIN_CHUNK_FRACTION` (4-chars-per-token estimate, consistent with the P95 cap in 6b)
- [x] When `MARKDOWN_MIN_CHUNK_FRACTION > 0.0`, replace the post-split nodes with the filtered list before metadata extraction
- [x] Log when chunks are dropped using `logger.info`

### 0.6 Pass-through to `is_markdown` branch

- [x] In `_read_and_chunk_file_async`, replace the fixed splitter construction with Markdown-specific `effective_chunk_size = MARKDOWN_CHUNK_SIZE if is_markdown else chunk_size`:
  ```python
  if is_markdown:
      md_chunk_size = MARKDOWN_CHUNK_SIZE  # may equal CHUNK_SIZE
      splitter = SentenceSplitter(chunk_size=md_chunk_size, chunk_overlap=CHUNK_OVERLAP)
  else:
      splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
  ```
- [x] Verify the non-Markdown branch is **byte-identical to current behaviour** (no behaviour change for `.txt`, `.pdf`, `.docx`, etc.) with an automated test

---

## Phase 1 — Run `top_k` sweep on the rebuilt 512-token candidate

No code changes other than `run_eval.py` flag plumbing. The Phase 1 candidate is rebuilt from the 6c-local corpus at `MARKDOWN_CHUNK_SIZE=512` and stored under `chroma_candidate_runs/baseline_6b/` for continuity with the 6b comparison.

### 1.1 Evaluator flag plumbing

- [x] Fork `experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py` to `experiments/6c-markdown-chunking-quickwins-2026-05-28/run_eval.py`
- [x] Add `--top-k INT` argparse flag (default 5)
- [x] Add `--candidate-dir PATH` argparse flag (default `./chroma_candidate_runs/baseline_6b`)
- [x] Wire `--top-k` into the `search()` call and the `top_k_*` reporting columns (sources, scores, sections, texts, relevance grades)
- [x] Record `top_k`, `baseline_dir`, and `candidate_dir` in the output JSON
- [x] Compute Evidence Recall at K ∈ `{1, 3, 5, 10, 20}` (values beyond requested `top_k` collapse to the available retrieval window rather than reporting `null`)
- [x] Compute nDCG@5 and nDCG@10

### 1.2 Run Phase 1 matrix

- [x] `1A-k5`  — Pass A, top_k=5,  rerank off, candidate=baseline_6b
- [x] `1A-k10` — Pass A, top_k=10, rerank off, candidate=baseline_6b
- [x] `1A-k20` — Pass A, top_k=20, rerank off, candidate=baseline_6b
- [x] `1B-k5`  — Pass B, top_k=5,  rerank on,  candidate=baseline_6b
- [x] `1B-k10` — Pass B, top_k=10, rerank on,  candidate=baseline_6b
- [x] `1B-k20` — Pass B, top_k=20, rerank on,  candidate=baseline_6b

### 1.3 Phase 1 stop rule

- [x] Read `1A-k10.json` and `1B-k10.json`. Phase 1 reached Pass B parity at `1B-k10` but did not produce a decisive Pass B lift, so it did **not** close the gap on its own
- [x] Continue to Phase 2; production recommendation is decided on the best cell in `results.md`

---

## Phase 2 — `chunk_size` sweep on the Markdown branch only

### 2.1 Parameterised candidate ingestion

- [x] Create `experiments/6c-markdown-chunking-quickwins-2026-05-28/ingest_candidate.py` from the 6b ingestion helper
- [x] Strip the baseline-build code path into a separate `ingest_baseline.py`; `ingest_candidate.py` builds candidate variants only
- [x] Add argparse flags: `--chunk-size INT`, `--heading-prepend`, `--min-size-floor FLOAT`, `--metadata-copy/--no-metadata-copy`, `--out-dir PATH` (required)
- [x] Set the corresponding env vars from the flags before importing `rag_mcp.ingestion` so `config.py` sees them
- [x] Verify the ingestion writes to `--out-dir`, not the global ChromaDB path

### 2.2 Run Phase 2 matrix

- [x] Build candidate at `chunk_size=768`: `ingest_candidate.py --chunk-size 768 --out-dir chroma_candidate_runs/c768`
- [x] Build candidate at `chunk_size=1024`: `ingest_candidate.py --chunk-size 1024 --out-dir chroma_candidate_runs/c1024`
- [x] `2A-c512`     — represented by Phase 1 `1A-k5`, candidate=baseline_6b
- [x] `2A-c768`     — Pass A, top_k=5,  candidate=c768 (`eval_results.2A-c768-k5.json`)
- [x] `2A-c1024`    — Pass A, top_k=5,  candidate=c1024 (`eval_results.2A-c1024-k5.json`)
- [x] `2A-c768-k10`  — Pass A, top_k=10, candidate=c768
- [x] `2A-c1024-k10` — Pass A, top_k=10, candidate=c1024
- [x] `2B-c768`     — Pass B, top_k=5,  candidate=c768 (`eval_results.2B-c768-k5.json`)
- [x] `2B-c1024`    — Pass B, top_k=5,  candidate=c1024 (`eval_results.2B-c1024-k5.json`)
- [x] `2B-c768-k10`  — Pass B, top_k=10, candidate=c768
- [x] `2B-c1024-k10` — Pass B, top_k=10, candidate=c1024

### 2.3 Phase 2 picks

- [x] Pick the best `(chunk_size, top_k)` cell by Pass B Evidence Recall@5: `chunk_size=1024`, reranker enabled, `top_k=5` or `top_k=10` (both 62.3% Evidence Recall@5)
- [x] Record the pick in `results.md` Phase 2 table
- [x] Defer Phase 3 because Phase 2 already found a production-shape winning configuration; heading-prepend/min-size-floor are recommended as a future Experiment 6d if Pass A needs improvement

---

## Phase 3 — Heading prepend (H) and min-size floor (F)

**Status: DEFERRED.** Phase 3 was not run in 6c because Phase 2 already found a production-shape winning cell (`chunk_size=1024`, reranker enabled). The scripts support H/F and `results.md` recommends them as a possible Experiment 6d if we want to improve Pass A.

### 3.1 Build candidates with H, F, and HF combined

- [x] Deferred — build candidate H: `ingest_candidate.py --chunk-size 1024 --heading-prepend --out-dir chroma_candidate_runs/h`
- [x] Deferred — build candidate F: `ingest_candidate.py --chunk-size 1024 --min-size-floor 0.5 --out-dir chroma_candidate_runs/f`
- [x] Deferred — build candidate HF: `ingest_candidate.py --chunk-size 1024 --heading-prepend --min-size-floor 0.5 --out-dir chroma_candidate_runs/hf`

### 3.2 Run Phase 3 matrix

- [x] Deferred — `3A-h`     — Pass A, top_k=<best>, candidate=h
- [x] Deferred — `3A-f`     — Pass A, top_k=<best>, candidate=f
- [x] Deferred — `3A-hf`    — Pass A, top_k=<best>, candidate=hf
- [x] Deferred — `3B-hf`    — Pass B, top_k=<best>, candidate=hf

### 3.3 Phase 3 decision

- [x] Phase 3 decision: defer H/F to a possible Experiment 6d because Phase 2 already produced the production-shape winner (`MARKDOWN_CHUNK_SIZE=1024` with reranker enabled)
- [x] Record H/F as not run in `results.md` and show the reproduction command for a future `c1024-hf` candidate


---

## Phase 4 — Defensive metadata copy (M) on the best cell

**Status: NOT RUN AS A SEPARATE PHASE.** M is always-on in the ingestion code and was therefore present in every candidate built after the hook was added (`baseline_6b`, `c768`, `c1024`). A separate M ablation was not run.

### 4.1 Run Phase 4 matrix

- [x] M was included in every rebuilt 6c candidate index after implementation; no separate `4A/4B` result files were produced

### 4.2 Phase 4 expectations

- [x] Not measured as an ablation — if metadata-copy impact matters, run a future `--no-metadata-copy` ablation
- [x] Evidence Recall results are recorded with M enabled in all rebuilt 6c candidate indexes

---

## Phase 5 — Write `results.md` and decision

### 5.1 Result aggregation

- [x] Collect all Phase 1 and Phase 2 `eval_results.<run-id>.json` files
- [x] Build the Phase 1 and Phase 2 summary tables
- [x] Pick the single best cell across completed phases by Pass B Evidence Recall@5: `2B-c1024-k5` / `2B-c1024-k10` (both 62.3%)
- [x] Per-query drill skipped — Phase 2 summary and plain-English diagnosis were sufficient for the production recommendation; detailed drill deferred unless a future 6d investigates Pass A failures

### 5.2 Write `results.md`

- [x] TL;DR / best-cell summary written in `experiments/6c-markdown-chunking-quickwins-2026-05-28/results.md`
- [x] Per-phase tables written for completed Phases 1–2; Phases 3–4 explicitly documented as not run / deferred
- [x] One-paragraph plain-English diagnosis written: `chunk_size=1024` reduces fragmentation enough for the reranker to win
- [x] Production recommendation written: promote `MARKDOWN_CHUNK_SIZE=1024` for Markdown only, keep global `CHUNK_SIZE=512`, keep reranker enabled
- [x] Best cell is positive in Pass B, so no second negative-result escalation is needed

### 5.3 Production recommendation outcome

- [x] **Selected outcome — `MARKDOWN_CHUNK_SIZE=1024` closes it in production shape.** Recommend promoting `MARKDOWN_CHUNK_SIZE=1024` to a different default than global `CHUNK_SIZE=512`. Open `5-experiment-6c-promote-defaults` that changes only the Markdown chunk-size default.

Non-selected outcomes, recorded for traceability:

- Outcome A — `top_k=10` alone reaches Pass B parity but does not produce the best lift; not selected.
- Outcome C — `MARKDOWN_HEADING_PREPEND=true` was implemented but not evaluated in Phase 3; defer to a possible Experiment 6d.
- Outcome D — `MARKDOWN_MIN_CHUNK_FRACTION=0.5` was implemented but not evaluated in Phase 3; defer to a possible Experiment 6d.
- Outcome E — multiple knobs jointly close it; not evaluated because Phase 2 already found a winner.
- Outcome F — no cell reaches Pass B parity; refuted by Phase 2 (`2B-c1024-k5` and `2B-c1024-k10`).

---

## Phase 6 — Tests

### 6.1 New test coverage in `tests/test_markdown_chunking.py`

- [x] **Metadata propagation on multi-chunk Markdown** — build a test fixture with one section longer than `MARKDOWN_CHUNK_SIZE` (forces second-stage `SentenceSplitter` to emit ≥2 sub-chunks). Assert that EVERY emitted node has a non-empty `metadata["header_path"]`. This is the test that did not exist in 6b.
- [x] **Defensive metadata copy idempotence** — call `_ensure_heading_metadata` twice on the same node list; assert no change on the second call
- [x] **Heading prepend on / off** — set `MARKDOWN_HEADING_PREPEND=true`, ingest a multi-section file, assert `node.text.startswith("[/")` for emitted nodes
- [x] **Heading prepend double-application guard** — set `MARKDOWN_HEADING_PREPEND=true`, run prepend twice; assert text is not double-prepended
- [x] **Min-size floor** — set `MARKDOWN_MIN_CHUNK_FRACTION=0.5`, ingest a file with one orienting `## Introduction\n\nWe study X.` chunk; assert that chunk is dropped from the output
- [x] **Backward compat** — with all three new env vars unset, assert ingestion produces byte-identical chunks to the 6b candidate (snapshot test against a small Markdown fixture)

### 6.2 Coverage thresholds

- [x] `rag_mcp/ingestion.py` must remain ≥ 95% line coverage per the modular floor in `AGENTS.md` — confirmed 96% in the 2026-05-29 full non-slow suite
- [x] Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm overall ≥ 90% — confirmed 388 passed, 2 deselected, 93% total coverage on 2026-05-29

---

## Phase 7 — Documentation

### 7.1 Code-level docs

- [x] Add docstrings to `_ensure_heading_metadata`, `_apply_heading_prepend`, `_drop_small_chunks`. Google style. Include a one-line "experimental knob — see OpenSpec change `4-experiment-6c-markdown-chunking-quickwins`" pointer.
- [x] Update `AGENTS.md` rule 13 (Markdown files use a chained heading-aware parser) with a one-line note about the three new env vars and their promoted / experimental status.

### 7.2 Env vars

- [x] Update `.env.example` with the three new vars, their defaults, and a comment block explaining their promoted / experimental status.

### 7.3 Change-log

- [x] No `CHANGELOG.md` entry until 6c writes its `results.md` and the follow-up `5-experiment-6c-promote-defaults` change ships. This change is experiment scaffold; user-visible behaviour is unchanged.
- [x] Conventional Commit prefix for the implementation commit: `chore(experiment): scaffold 6c markdown chunking quick-wins`. The follow-up promotion change will use `feat:` if defaults move.

---

## Phase 8 — OpenSpec validation and archive prep

- [x] `openspec validate 4-experiment-6c-markdown-chunking-quickwins` — passed with `--strict` on 2026-05-29
- [x] After 6c results are written and any follow-up `5-experiment-6c-promote-defaults` change has shipped, archive 4 with `openspec-archive-change` skill

---

## Out of scope (deferred to a separate OpenSpec proposal)

The following are **explicitly not** in this change. They are gated on 6c outcomes (Phase 5 step 5.3 outcome F):

- `HierarchicalNodeParser([1024, 512])` + `AutoMergingRetriever` integration. Cross-module change touching `ingestion.py` and `retrieval.py`, requires a `SimpleDocumentStore` + `StorageContext`, and changes the `search()` output shape. Right answer in principle for "right paper, wrong section" if 6c's small-bore interventions are insufficient.
- Anthropic-style contextual retrieval via local Ollama `qwen3:0.6b` (1–2 sentence chunk summaries prepended before embedding). Reported gains are large (35% retrieval-failure reduction in Anthropic's published numbers) but ingestion latency rises by 7–14 minutes on the 20-paper corpus and the `_read_and_chunk_file_async` control flow becomes meaningfully more complex.
- A `SemanticSplitterNodeParser`-based replacement for the second-stage `SentenceSplitter`. Embeds during ingestion (slow) and needs threshold calibration; the speed and tuning cost are disproportionate to the expected lift relative to the four 6c interventions.
- Switching corpora from Qasper to MultiHop-RAG / GutenQA. The 6b corpus is already evidence-dense and the failure mode is well characterised; a corpus swap is a separate methodological question, not a chunker tuning question.

These will be revisited only if 6c's `results.md` records outcome F (no cell reaches Pass B parity).
