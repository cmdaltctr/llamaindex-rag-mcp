# Evidence: ingestion graph adapters and fingerprints (tasks 3.4 and 3.5)

Date: 2026-10-13. Branch: `feat/add-local-web-pipeline-workspace`.
Command prefix for every run below:

```bash
PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>
```

## Scope

- 3.4 (adapter part): graph adapters and `OperationDescriptor`s for the Sources, Read, Prepare text, and Embed / commit families.
- 3.5: index-shaping fingerprint of an ingestion graph, and its place in the source index identity.

## Files

| File | Lines | Contents |
| --- | --- | --- |
| `src/omrg/core/ingestion/graph_adapters.py` | 427 | Adapters, `register_ingestion_operations`, `ingestion_unit_split`, `source_unit_id`. |
| `src/omrg/core/ingestion/graph_adapters_catalogue.py` | 320 | Port types, parameter models, descriptors, `canonical_ingestion_definition`. |
| `src/omrg/core/ingestion/graph_adapters_values.py` | 182 | `SourceWork` port value, resource helpers, `run_protected`. |
| `src/omrg/core/ingestion/graph_fingerprint.py` | 213 | `IngestionShape`, `graph_shape`, `ingestion_shape`, `standard_shape`. |
| `src/omrg/core/ingestion/source_state.py` | 489 (+5) | `build_index_identity(..., graph_shape=None)`. |
| `src/omrg/core/ingestion/sources.py` | 355 (+7) | `IngestionContext.graph_shape` and the matching `build_ingestion_context` keyword. |

`sources.py` is not an owned file. The identify adapter cannot pass the shape to `build_index_identity` through `prepare_source` without it. The edit is additive: the new field defaults to `None`, and `None` keeps every existing digest.

## Operations

| Operation | Family | Seam | Effect | Shaping |
| --- | --- | --- | --- | --- |
| `source.discover` | sources | `gather_supported_files`, `detect_content_types`, `iter_source_units` | read_only | no |
| `source.identify` (new id) | sources | `prepare_source`, `check_source_state` | read_only | no |
| `read.document` | read | `chunk_specialised_source`, then `read_document` | read_only | yes |
| `prepare.normalise` (new id) | prepare | `normalise_backend_read` | pure, bypass | yes |
| `prepare.enrich` (new id) | prepare | `enrich_documents` with explicit `store` and `settings` | model_call, bypass | yes |
| `prepare.chunk` | prepare | `declares_markdown`, `split_documents` | pure | yes |
| `embed.chunks` | embed | `prepare_source_embeddings` | model_call | yes |
| `commit.source` | commit | `commit_prepared_source` | source_commit | no |

Canonical graph: the eight nodes above in this order, with one graph input `path` and one output `summary`.

Rules the adapters keep:

1. One `SourceWork` value carries one source from identify to commit. An unchanged or binary source passes through every node without work.
2. `source.identify` accepts exactly one unit. It refuses a whole directory list with an actionable message, so a graph cannot materialise a directory's chunks.
3. `source.identify` runs the legacy-lineage guard and the complete-version check before any read.
4. `read.document` keeps the `BackendRead` value. `prepare.chunk` reads `text_format` and `structured` from it unchanged.
5. `embed.chunks` stamps lineage and embeds outside the write lock. The norm guard fails here, before any write.
6. `commit.source` is the only adapter that mutates the store. It checks that the reuse check used the same collection. It checks `context.cancellation` before it starts. It runs the commit through `run_protected`: once started, the write, verification and stale cleanup finish, also when the awaiting task is cancelled.
7. A binary unit's stale-row cleanup also runs only in `commit.source`.
8. Resources come only from `context.resource(...)`. Settings come only from `context.settings`. Blocking seams run with `asyncio.to_thread`.

## Fingerprint (task 3.5)

- The fingerprint hashes the ancestor slice of the one enabled `source_commit` node.
- Each index-shaping node adds its operation id, resolved version, enabled state, validated parameters (collection parameter removed) and the hashes of its inputs in port order.
- A node that is not index shaping (discover, identify, commit) is transparent. It forwards the hashes of its own inputs.
- Node ids, layout, titles, the destination collection and query-only branches do not count.
- Two enabled commit nodes raise `ValueError` (one destination per recipe).
- `SHAPE_SCHEMA = 1` versions the algorithm and the identity block.

Shared description: the canonical graph defines the *standard shape*. `ingest_path_async` and the canonical graph both build the identity with no `graph_shape` block. Any other shape adds `{"schema": 1, "fingerprint": ...}` to the identity payload.

### Decision for the lead: no one-off reprocessing

`_INDEX_IDENTITY_SCHEMA` stays at 6. The standard shape adds nothing to the payload, so every existing `source_index_identity` stays the same. Existing collections do not reprocess. Only sources ingested through a non-standard graph get a new identity, and they reprocess once on their next explicit ingest. `test_standard_identity_digest_is_unchanged` pins this.

If the lead prefers the block on every identity, bump the schema to 7. Then every existing source reprocesses once on its next explicit ingest.

## Test-first record

New tests (50):

- `tests/unit/test_ingestion_graph_adapters.py` (17): catalogue contract; vector-only commit port; canonical preflight; parity with `ingest_path_async` (rows, chunk ids, identities, per-source outcomes, effects); reuse skips reads; reader-declared Markdown reaches the splitter; one unit per pass; binary cleanup only in commit; non-commit nodes never mutate the store; no process defaults; missing `store`, `embedder` or `ingestion_shape` fails; the real `run_pipeline` with `ingestion_unit_split()` writes the same rows.
- `tests/unit/test_ingestion_graph_adapters_commit.py` (10): NaN vectors; three invalid-lineage cases; legacy lineage before parse; failed verification keeps the previous version and a retry cleans; cancellation before commit; cancellation during commit; task cancellation waits for an entered commit; collection mismatch.
- `tests/unit/test_ingestion_graph_fingerprint.py` (18): layout, node ids, destination, query-only branch and explicit inherit keep the shape; parameter, connection, disabled node and version change it; identity block; admitted shape equals saved shape.
- `tests/unit/test_ingestion_graph_fingerprint_reuse.py` (5): standard digest unchanged; layout change reuses standard sources; shaping change reprocesses once, then reuses; connection change reprocesses; admitting a changed graph writes nothing.
- `tests/unit/test_ingestion_graph_adapters_support.py`: helpers only (real admission, hand-chained adapters).

| Step | Result |
| --- | --- |
| Red, before implementation | 4 collection errors (modules absent) |
| Green, after implementation | 50 passed |

Mutation checks. Each mutation was restored, and the restored files were compared byte for byte:

| Mutation | Result |
| --- | --- |
| Identify passes `graph_shape=None` | 2 failed, 48 passed |
| Commit skips the cancellation check | 1 failed, 49 passed |
| `run_protected` without shield | 1 failed, 49 passed |
| Commit ignores the reuse-check collection | 1 failed, 49 passed |
| All restored | 50 passed |

## Regression record

| Set | Result |
| --- | --- |
| 3 seam files (`tests/unit/test_ingestion_seams*.py`) | 39 passed |
| Focused set from `ingestion-seams.md` (25 files) plus the 4 new files, `-m "not slow"` | 439 passed, 17 skipped |
| Other identity users: `test_engine.py`, `test_ocr_route_identity.py`, `test_profile_scoped_extensions.py`, `test_query_embedding_instruction.py`, `test_pipeline_import_boundaries.py`, `unit/test_pipeline_guide.py` | 104 passed, 1 failed |

The one failure is `test_engine.py::test_engine_public_method_surface_is_exactly_documented`. It reports the new `run_pipeline`, `validate_pipeline` and `resolve_settings` Engine methods from another agent's work. These files do not touch `Engine`.

Other checks:

- `ruff check` and `ruff format --check` on all touched files: pass.
- `lint-imports`: 12 contracts kept, 0 broken.
- The accessor-guard scanner (`_scan_default_accessors`, `_scan_text`) finds nothing in the four new modules.

## What the runner and Engine must do

1. Run ingestion graphs with `units=ingestion_unit_split()` (`UnitSplit(node="discover", port="sources", unit_id=source_unit_id)`). Unit ids are paths relative to the ingested root.
2. Compute `ingestion_shape(snapshot, catalogue)` once per admitted run. Pass it as resource `"ingestion_shape"`. A missing shape fails the identify node; there is no silent default.
3. Pass resources `"store"` and `"embedder"`. Pass `"ocr"` when the host has an OCR client. Without it, the graph reads with OCR unavailable. `ingest_path_async` composes an operation-owned OCR client when `ocr_fallback_enabled` is on; the graph does not, because provider construction is host-owned.
4. Each unit's `summary` output is the `ingest_path_async` file-detail dict (`file`, `status`, `chunks`, `source_version`, plus `source_id`, `chunks_removed`, `timings`, `effective_strategy`, `embedding_norm_band` when present). A failed unit has no summary; map its error from `UnitOutcome.error`.

## Deviations and open items

1. Code and configuration sources are split by their registered strategy inside `read.document`, as in `read_and_chunk_file_async`. This keeps content-type precedence without a second dispatch rule. So `prepare.chunk` levers do not change code/config sources; `read.document` exposes `chunking.strategy_fallback` and `chunking.code_chunk_lines` instead.
2. A node-level lever parameter counts in the fingerprint as written. An explicit value equal to the default therefore reprocesses once. This is conservative and safe.
3. `source.discover` reports unsupported files only as a count in its event summary.
4. For task 3.8, add these modules to `_GUARDED_LEAVES` in `tests/test_no_global_settings_reads.py`: `core/ingestion/graph_adapters.py`, `graph_adapters_values.py`, `graph_adapters_catalogue.py`, `graph_fingerprint.py`.
