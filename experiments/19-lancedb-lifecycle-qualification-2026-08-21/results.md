# Results — campaign 19, LanceDB production-lifecycle qualification

## Verdict

**PASS** (run2, 14/14 gates) at commit `a57abf372db521f201788662591da14c4dceabe0`,
lock hash `3a225230a6eb…`, Ollama `nomic-embed-text` embeddings,
`vector_store=lancedb` (embedded, `dense_similarity_v1`), corpus identity
`sha256:ec1d5…`. The gate-0 pause condition for the default flip
(tasks 2.1–2.3 of `make-lancedb-default-and-isolate-chromadb`) is met by
this run.

## Run lineage

| Run | Verdict | Cause |
| --- | --- | --- |
| run1 | FAIL (12/14) | harness defects, not product defects: G2 searched the default `documents` collection in the fresh interpreter; G7's v1-only marker word also occurred in the v2 text |
| run2 | PASS (14/14) | harness corrected in `a57abf3`; unchanged production code between runs |

## Per-gate results (run2, derived from `output/run2/raw_rows.jsonl`)

| Gate | Verdict | Key observation |
| --- | --- | --- |
| G1 real write | pass | 3 files parsed/chunked/embedded/written; 5 chunks; 1.0 s |
| G2 restart/reopen | pass | fresh interpreter reopened the same URI: count 5/5, dense hit `alpha_quartz.md` |
| G3 dense | pass | all 3 gate queries returned the expected source file as top hit |
| G4 BM25 hybrid | pass | fused query returned 5 rows; top file `bravo_harbour.txt` |
| G5 metadata filters | pass | filter returned 3 rows, all from `alpha_quartz.md`; `count_where` = 3 |
| G6 unchanged re-ingest | pass | chunk count 5 → 5; change detection skipped all files |
| G7 replacement | pass | 1 chunk removed + 1 created; v1-only marker absent, v2 phrase present |
| G8 document deletion | pass | 1 chunk removed; count 5 → 4; harbour file no longer retrieved |
| G9 collection deletion | pass | collection absent from listing after delete; recreated and re-ingested (3 chunks) |
| G10 identity stamping | pass | table metadata carries `rag_embed_provider`/`rag_embed_model`; model matches manifest |
| G11 generation invalidation | pass | generation advanced 8 → 9 on a real write (no explicit bump); post-mutation hybrid top hit is the new document |
| G12 interrupted-write recovery | pass | bounded failure contained to `broken_binary.pdf` (failure reported); `good_delta.txt` queryable; subsequent clean ingest healthy |
| G13 narrowed-lock concurrent read | pass | dense search completed in 0.033 s while an ingestion into a second collection was in flight (TDR-013 lock scope; `lock_wait_seconds` ≈ 7e-7 in ingest timings) |
| G14 manifest + plan agreement | pass | preflight errors `[]`; mandatory manifest fields non-null; plan cells == executed gates |

## TDR-014 admissibility

- Manifest frozen before gates at a clean commit; raw rows append-only;
  verdicts written atomically per gate.
- Permitted nulls carry reasons (e.g. `reranker.*`: reranking disabled for
  this campaign; `chunking.*` observation not applicable — the chunker is
  exercised through the real ingest path in G1).
- `output/run2/lancedb_store/` is the qualified index directory referenced
  by task 6.4 (freeze the qualified LanceDB index before Stage 6).

## Scope note

The qualification exercises production lifecycle semantics of the LanceDB
adapter and pipeline. Later tasks of the same OpenSpec change must not
alter `core/vectordb/lancedb*.py` behaviour; task 8.4 verifies this via
diff inspection. If any later commit touches those modules' behaviour,
this campaign must be re-run before the default flip lands.
