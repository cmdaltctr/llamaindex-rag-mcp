# Experiment 4 results — BM25 cache isolation and invalidation

**Status: PASS** (all five correctness gates green in every cell)
**Executed:** 2026-08-19, worktree `harden-pipeline-correctness-before-calibration`
**Commit:** `c475852cf195658ce6af8654e11e07dce4c39fec` (dirty: experiment artefacts uncommitted)
**Runtime:** Python 3.12.10, chromadb 1.5.9, lancedb 0.37.1, rank_bm25 NOT
installed — the deterministic internal `_SimpleBM25Okapi` mirror
(sparse.py:93-151) served the sparse path; every manifest records this
honestly as `sparse.effective_backend: "bm25-internal-okapi"`.
**Protocol:** `protocol.md` v1.0, pre-registered sections unchanged; execution record appended there.

## Hypothesis verdicts (4 cells: {chroma, lancedb} × {forward, reversed})

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 store isolation | **PASS** | 0 cross-store contaminations across all 60 query rows; two DISTINCT cache entries for the two same-named `documents` collections observed at the equal-generation collision step (`documents_key_entries == 2`) in every cell |
| H2 collection isolation | **PASS** | 0 cross-collection contaminations within store A; every (namespace, token, phase) result matched the pre-registered expected ids exactly (0 mismatches) |
| H3 stable reuse | **PASS** | 6 repeated unmutated queries per cell (24 total) caused 0 additional cache builds |
| H4 mutation invalidation | **PASS** | Every affected-namespace post-mutation query rebuilt exactly once (build delta 1); unaffected totals held in all 4 cells: B/documents 1 build, A/other 3, A/documents 5 |
| H5 single generation owner | **PASS** | All 36 recorded mutations advanced the generation by exactly +1 — direct path (`upsert_precomputed`, `delete_where`, `delete_collection`, recreate) AND production-orchestration path (`embed_and_write_async`, `remove_document`) |

## Actual cache keying mechanism (reported as-is, not redesigned)

- `BM25SparseRetriever._cache` is a class-level dict at
  `src/rag_mcp/core/retrieval/sparse.py:183`.
- Key: `(store.cache_identity, collection_name)` built in
  `_cache_key()` (`sparse.py:244-247`); `cache_identity` defaults to the
  store object itself (`src/rag_mcp/core/vectordb/base.py:22-25`).
- Invalidation: `_get_or_build_index` (`sparse.py:249-263`) rebuilds
  when the store's per-collection generation
  (`VectorStore.get_generation`) differs from the cached entry.
- Build instrumentation wraps the module seam
  `_read_collection_rows` (`sparse.py:266`), called exactly once per
  rebuild; counts recorded per (store label, collection).

## Step 9 orchestration choice (documented)

The production-orchestration path is the ingestion WRITER API:
`embed_and_write_async` (`src/rag_mcp/core/ingestion/writer.py:31`)
with pre-embedded `TextNode`s (no embedding model call — nodes carry
their vectors; `MockEmbedding` stands in only for the writer's
`model_name` log line) plus `remove_document` (`writer.py:157`).
Minimal honest path below `ingest_path_async`: it drives the real
`write_nodes` mutation contract (generation ownership, write lock,
store dispatch) without dragging parsing/chunking into a sparse-cache
experiment. Generation deltas matched the direct-store sequence
exactly (+1 each). The Factor C level-4 collection delete/recreate
battery runs after the comparison.

## Manifest identities (per cell)

All four cells share: `repo_commit`
`c475852cf195658ce6af8654e11e07dce4c39fec`, `dependency_lock_hash`
`3a225230a6ebe0f7…` (sha256 of `uv.lock`), corpus
`sha256:cfe8b9aa1a98…` (`fixtures/docs.json`), queries
`sha256:99811e9e5f19…`, qrels `sha256:7bb1e5b2cc48…`.

| Cell | index_identity |
|---|---|
| `chroma_forward` / `chroma_reversed` | `exp4-namespaces::chroma::cfe8b9aa1a98` |
| `lancedb_forward` / `lancedb_reversed` | `exp4-namespaces::lancedb::cfe8b9aa1a98` |

Full hex values in each cell manifest inside `output/run1/results.raw.json`.

## Preflight (TDR-014 / protocol §12)

Plan agreement green; per cell `build_runtime_manifest` with hybrid
active (`sparse.effective_backend` non-null) and the protocol §12
battery asserted from recorded observations: stores distinct instances,
both hold a collection literally named `documents`, contents verified
different, collision generations equal (both 1 after setup), cache
starts empty. Controlled constants pinned across the 4 cells.

## Determinism proof

Two full executions → canonical projections byte-identical:
`sha256:ef3e15d179819e6b01a7dbe89a61277d51adc8de58225897778871a3432662c3`
(both files); see `output/deterministic_rerun_proof.txt`.
Canonicalisation removes `latency_ms`, `timestamp_utc`, random cleanup
paths, rounds floats to 9 dp.

## Reproduction

```bash
uv run --no-sync python experiments/example/experiment-4-bm25-cache-isolation/run_eval.py \
  --output-dir experiments/example/experiment-4-bm25-cache-isolation/output/run1
uv run --no-sync python experiments/example/experiment-4-bm25-cache-isolation/summarise_eval.py \
  experiments/example/experiment-4-bm25-cache-isolation/output/run1/results.raw.json
```

Fixtures regenerate deterministically with `make_fixtures.py` (committed
JSONs are the ground truth).

## Artefacts (all verified non-gitignored)

- `fixtures/docs.json`, `fixtures/queries.json`, `fixtures/qrels.json` — committed BEFORE runs
- `plan.json` — 4 cells, loadable via `ExperimentPlan.from_json`
- `output/run1/`, `output/run2/` — `results.raw.json` (60 D16 rows, 36-mutation traces, build counters, manifests), `results.summary.json`, `results.canonical.json`, `cells/<cell>.json`
- `output/deterministic_rerun_proof.txt`

## Cleanup (protocol §20)

Temporary store directories (4 per run) deleted after raw results were
saved — paths recorded in each raw file's `cleanup` list; 0 leftover on
disk at close. `BM25SparseRetriever._cache` cleared before every
battery and restored-cleared after.

## Judgement calls

1. **Three stable documents per namespace** (token carrier + two
   fillers): BM25 IDF for a df=1 term is non-positive at N≤2 (negative
   IDF clipped to a negative epsilon, or exactly 0 at N=2), so a
   1-or-2-doc namespace would score every rare token ≤ 0 and return
   nothing — a fixture artefact, not a cache property. Three docs keep
   df=1 IDF positive in every phase.
2. **Reversed sequence** = literal reversal of the initial distinct
   namespace first-queries (A/other → B/documents → A/documents), with
   the cross-store probe mirrored; the mutation battery (steps 5-9) is
   order-invariant and therefore unchanged.
3. **Per-cell store instances live in `tempfile` roots** rather than
   the repo, so protocol §20 cleanup needs no repo-local gitignore
   entries; BM25 build counting uses store labels (A/B), never `id()`
   values, keeping raw files deterministic across runs.
4. `retrieval.threshold_score_kind` recorded as the honest string
   `"not_applied"` (no threshold is evaluated in a sparse-only battery)
   rather than inventing a score-kind name.
5. The collection delete/recreate battery (Factor C level 4) extends
   the §8 sequence after step 9; an intent-only `create_collection`
   does not bump generation, so the drop (+1) and the recreate upsert
   (+1) are the two mutations counted.
