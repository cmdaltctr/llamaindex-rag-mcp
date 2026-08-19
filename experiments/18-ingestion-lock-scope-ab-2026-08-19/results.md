# Experiment 18 results — Stage 3B lock-scope baseline (Phase A)

**Date:** 2026-08-19 · **Operator:** Dr Muhammad Aizat Bin Md Hawari
**Status:** Phase A complete — see verdict below; Phase B A/B conditional
**Environment:** macOS aarch64, Python 3.12.10, `uv sync --frozen` (208 packages),
ChromaDB local persistent (isolated per cell), real block = Ollama
`nomic-embed-text` at `http://localhost:11434`. Runtime manifests with
`repo_commit`, `dependency_lock_hash`, and `corpus_identity` are recorded inside
every cell JSON (`output/cells/*.json`).

## Phase A gates — all PASS

| Gate | Evidence |
| --- | --- |
| H1 bounded units | max chunks/file constant (2 chunks/file) at 25/100/400 files; 400-file ingest retained one source at a time |
| H2 RSS scaling | peak RSS 25→100 files grew within the ≤2.0 guard (fake block, no model-load noise) |
| H3 failure safety | parse / embed / store-write injection during version-B replacement: version-A rows survived in all three cells (2→2 rows; observed failure stages `file`/`embedding`/`store_write`) |
| H4 swap | post-fault recovery ingest replaced A with B exactly in all four cells (row count == chunk count, single version present) |
| H5 unchanged skip | second identical ingest skipped 100% of files, zero chunks created |

Numbers: `output/results.summary.json`; per-cell raw timings in
`output/cells/`.

## Lock-scope timing evidence (the D12 decision data)

Deterministic 100-file corpus, ~2 chunks/file, fresh isolated store per cell,
one subprocess per cell.

| Cell | Wall (s) | Lock wait (s) | Lock-wait / wall | Docs/s |
| --- | --- | --- | --- | --- |
| sequential, fake embed | 3.398 | 0.000 | 0.000 | 29.43 |
| 2-stream contended, fake embed | 2.994 | 0.490 | 0.164 | 32.73 |
| sequential, real Ollama embed | 18.994 | 0.0001 | ~0.000 | 5.26 |
| 2-stream contended, real Ollama embed | 18.963 | 18.120 | **0.956** | 5.27 |

Speedup of contended vs sequential (same 100 files): fake 1.14, real
**1.002** — with real embeddings the two streams are fully serialised by the
global `write_lock`, because embedding happens inside the lock and dominates
the lock-held critical section (sequential wall is ~19 s of which embedding is
the overwhelming majority; store write + verify + cleanup are sub-second per
hundred files in the fake block).

Single-stream lock wait ≈ 0 in both blocks — expected by construction:
`ingest_path_async` is a sequential per-file loop, so one ingest operation can
never contend with itself.

## Verdict against design.md §D12

**Lock scope demonstrably limits embedding throughput** — but only for
*concurrent* ingest operations (daemon dual-ingest, concurrent MCP tool
calls): contender lock wait is 95.6% of wall and contended speedup is 1.002,
i.e. zero effective parallelism while the holder embeds. The D12 condition
for a follow-up change is met with data.

Scope limits recorded before implementing:

- Moving embedding outside the lock cannot change single-stream throughput
  (the per-file loop is sequential; overlapping embed(N+1) with write(N) is a
  pipeline restructuring outside task 3.6.2's scope).
- `VectorStore.upsert_precomputed` cannot reproduce `write_nodes` row
  identity/metadata layout (see `design-notes.md`), so the minimal change
  keeps `write_nodes` inside the lock — nodes arrive pre-embedded and the
  adapter reuses populated embeddings, which satisfies "precomputed
  embeddings" without a store-contract change.
- Stamp-then-embed reordering is vector-neutral: `stamp_source_attempt`
  adds every source key to `excluded_embed_metadata_keys`, and row IDs are
  derived during stamping (`source_state.py`), so hoisting stamp+embed above
  the lock leaves vectors and IDs bit-identical.

Phase B (task 3.6.4) runs the A/B with the minimal narrow-lock change and the
H6 gate (≥20% contended docs/s) plus H7 (≤1.25× peak RSS, H1–H5 stay green);
the change is retained only if both pass.

## Threats and attribution limits

`embedding_seconds` includes embed-semaphore acquire; durability verification
and stamping sit in the untimed residual (see `design-notes.md`). Fake
embeddings isolate orchestration, not Ollama behaviour — hence both blocks.
macOS `ru_maxrss` includes the interpreter baseline; per-cell subprocesses
bound attribution to one cell.

## Cleanup

Generated corpora and per-cell Chroma directories live under `output/`
(gitignored); cell JSONs and summaries are committed. Remove `output/`
subdirectories after results are retained.
