## 1. Baseline and failing enforcement

- [x] 1.1 Create branch `refactor/complete-architecture-v2-conformance` off `main` and record the pre-change baseline in `openspec/changes/complete-architecture-v2-conformance/notes/baseline.md`: `uv run pytest -m "not slow" --cov=rag_mcp` totals per coverage tier, `uv run lint-imports` output, `wc -l` for every file over 400 lines under `src/rag_mcp/`, the starting test-file count and test count (`uv run pytest --collect-only -q | tail -1` plus `ls tests/**/*.py | wc -l`), and the count of test files that patch `rag_mcp.config.settings` — so the group 11 migration scope is auditable after the fact rather than estimated.

> **Coverage gate suspension (design.md, Risks §4).** From group 2 through group 11, intermediate commits run `uv run pytest -m "not slow"` **without** `--cov`. Coverage attribution is broken by the relocations and splits, so a `--cov` run at those boundaries fails on attribution drift rather than logic. The AGENTS.md floors are re-asserted at group 12 and again at 14.1; no commit reaches `main` without 14.1 passing.

> **Stale knowledge graph (design.md, Risks §7).** Between group 2 and group 13 the graphify graph does not describe the working tree. AGENTS.md's "query graphify before grep" rule is suspended for that window: any graphify result must be verified against the working tree before being acted on. Intermediate refreshes run at 2.9 and 9.8.
- [x] 1.2 Add import-linter contract `chromadb-confined-to-vectordb` to `pyproject.toml` (forbidden: `rag_mcp` → `chromadb`, `ignore_imports = ["rag_mcp.core.vectordb.chroma -> chromadb"]`) and confirm it FAILS today on `src/rag_mcp/codebase_map.py:476`.
- [x] 1.3 Add contract `config-is-leaf` (forbidden: `rag_mcp.config` → `rag_mcp.core.ingestion`, `rag_mcp.core.retrieval`, `rag_mcp.core.metadata`, `rag_mcp.core.vectordb`, `rag_mcp.core.profiles`, `rag_mcp.core.providers`, `rag_mcp.compose`, `rag_mcp.transports`, `rag_mcp.integrations`, `rag_mcp.daemon`) and confirm it FAILS today on `config/__init__.py:395`.
- [x] 1.4 Add contract `integrations-are-leaves` (forbidden: `rag_mcp.integrations` → `rag_mcp.core`, `rag_mcp.transports`, `rag_mcp.daemon`, plus the top-level graph modules) and confirm it FAILS today on `integrations/magika.py:81`.
- [x] 1.5 Add `tests/test_file_size_ceiling.py` asserting no file under `src/rag_mcp/**/*.py` exceeds 500 lines, reporting each offender with its line count; mark it `xfail(strict=True)` with a reference to task 8.6 and confirm it currently fails on the five known files.
- [x] 1.6 Add `tests/test_no_global_settings_reads.py` asserting zero occurrences of a resolved-settings singleton import under `src/rag_mcp/core/` and `src/rag_mcp/integrations/`; mark `xfail(strict=True)` referencing task 5.7 and confirm it currently reports all **25** sites. (Design D1 originally said 21; group 2's relocation moved four more into scan scope — see 5.6a. The scan covers `core/` and `integrations/` only; `transports/` reads are legitimate.)
- [x] 1.7 Commit the failing enforcement as a single `test:` commit so the pre-fix failure state is recorded in history.

## 2. Relocate the unmigrated v1 subsystems (Category B)

- [x] 2.1 Create `src/rag_mcp/core/codebase/__init__.py` and `src/rag_mcp/core/documents/__init__.py` with module docstrings stating they are namespace groupings, not strategy folders (no registry).
- [x] 2.2 `git mv src/rag_mcp/codebase_map.py src/rag_mcp/core/codebase/codebase_map.py` and fix its relative imports.
- [x] 2.3 `git mv src/rag_mcp/code_graph.py src/rag_mcp/core/codebase/code_graph.py` and fix its relative imports.
- [x] 2.4 `git mv src/rag_mcp/doc_graph.py src/rag_mcp/core/documents/doc_graph.py` and fix its relative imports.
- [x] 2.5 Rewrite `core/ingestion/pipeline.py:97`'s `from ...codebase_map import detect_file_types` to import from `rag_mcp.core.codebase`, removing core's upward import into a top-level module.
- [x] 2.6 Update every remaining consumer of the three moved modules (`transports/mcp.py`, `transports/cli/*`, `daemon/watcher.py`, `compose.py`, `integrations/magika.py`) to the new paths.
- [x] 2.7 Update all test imports of `rag_mcp.codebase_map`, `rag_mcp.code_graph`, `rag_mcp.doc_graph` to the `core.codebase` / `core.documents` paths, including monkeypatch targets.
- [x] 2.8 Run `uv run pytest -m "not slow"` (no `--cov` — see the group 1 coverage-gate note) and confirm green with no assertion changes.
- [x] 2.9 Run `graphify update .` so the knowledge graph reflects the relocated `core/codebase/` and `core/documents/` packages before any later group consults it.

## 3. Make the strategy registries the real dispatch (F1, F9)

- [x] 3.1 Rewrite `core/chunking/registry.py` to the PROPOSAL §4.4 contract: private `_registry`/`_cache` dicts, public `register(name, import_path)`, `get(name)`, `available()`; registrations record `"module:attr"` strings only.
- [x] 3.2 Apply the same rewrite to `core/metadata/registry.py` and `core/retrieval/registry.py`; align `core/providers/embeddings/registry.py` and `core/providers/llm/registry.py` to the identical public API.
- [ ] 3.3 **(reopened — partially done)** Replace the eager strategy imports at `core/ingestion/chunker.py:25-32` with `chunking_registry.get(<strategy>)` resolution at dispatch time; keep content-type precedence (AGENTS.md gotcha #8) byte-for-byte. **Remaining:** `markdown` is not registered at all; `chunker.py:190,201-205` still import `sentence`/`markdown` directly (moved to function scope, which is not dispatch); selection is still an if/elif ladder on `group`/`ts_lang`. §4.4 rule 4 is not yet true for chunking.
- [ ] 3.4 **(reopened — partially done)** Replace the if/elif backend chain at `core/metadata/extractor.py:36-39` and `:187-193` with `metadata_registry.get(<mode>)`, preserving the `disabled` short-circuit without resolving a backend. **Remaining:** the if/elif chain at `:185-198` survives with hardcoded literal registry keys, and `_dispatch_local_extraction:63-68` branches on `local_backend`. The spec forbids an if/elif chain over strategy names explicitly — registry indirection with a literal key is import-hiding, not dispatch.
- [x] 3.5 Replace the eager dense/fusion/policy/reranker imports at `core/retrieval/pipeline.py:19-27` with `retrieval_registry.get(...)` resolution.
- [x] 3.6 Have `compose.py` resolve the *active* chunking, metadata, and retrieval strategies at startup so a bad `register()` import string fails fast rather than at first query.
- [x] 3.7 Extend `tests/test_registry_contract.py` to walk `available()` → `get()` for every registered name in all five registries, asserting no `ImportError`, and to assert importing a registry imports no strategy module (check `sys.modules`).
- [x] 3.8 Add tests asserting `core/ingestion/chunker.py`, `core/metadata/extractor.py`, and `core/retrieval/pipeline.py` contain no module-level import of a concrete strategy module.
- [x] 3.9 Run `uv run pytest -m "not slow"` and confirm identical chunking, extraction, and retrieval behaviour.

## 4. Introduce the EffectiveSettings value object

- [x] 4.1 Add an `effective_settings(**overrides)` factory fixture to `tests/conftest.py` that builds a valid `EffectiveSettings` with sensible defaults, so later test migrations are one-line changes.
- [x] 4.2 Create `src/rag_mcp/core/settings.py` holding the frozen `EffectiveSettings` model: nested `chunking`/`ingestion`/`retrieval`/`metadata` blocks (the `ingestion` block per D10) plus the cross-cutting fields `core/` needs (`embed_model`, `chroma_persist_dir`, `collection_name`, `chroma_scan_page_size`, `pdf_reader`, `document_backend`, Azure fields, `magika_binary`, `doc_similarity_threshold`, codebase-map limits, `rag_profile`). No imports from `config`, `compose`, or sibling `core/` modules.
- [x] 4.3 Move `EffectiveSettings` out of `core/profiles/resolver.py:48` to the new module, re-exporting from `core.profiles` for the resolver's callers; keep `_bundle_to_effective` behaviour identical.
- [x] 4.4 Add a `Settings.to_effective()` (or equivalent adapter in `compose.py`) producing the server-default `EffectiveSettings`, and make `ProfileResolver` overlay only the profile-owned levers onto it.
- [x] 4.5 Replace `ProfileResolver`'s `from ...config import settings` at `core/profiles/resolver.py:263` with a `server_default_profile: str` constructor argument supplied by `compose.py`.
- [x] 4.6 Add unit tests: `EffectiveSettings` is frozen (mutation raises); two instances with different `rerank_enabled` are independent; `core/settings.py` has no upward imports.

## 5. Thread settings through core and delete the global

- [ ] 5.1 Type `ingest_path_async`'s `effective_settings` parameter (`core/ingestion/pipeline.py:31`) as `EffectiveSettings` and add the same parameter to `search()` (`core/retrieval/pipeline.py:148`); both required on the internal call path, resolved by the caller.
- [ ] 5.2 Thread the parameter through the ingestion chain and remove the global reads at `core/ingestion/_state.py:17`, `core/ingestion/chunker.py:19`, `core/ingestion/pipeline.py:16`, `core/chunking/markdown.py:12`, `core/chunking/sentence.py:18`.
- [ ] 5.3 Thread it through the retrieval chain and remove the global reads at `core/retrieval/pipeline.py:16,40`, `core/retrieval/policy.py:61,225`, `core/retrieval/reranker.py:36`, `core/retrieval/fusion.py:9`. Do not alter the ÷30 threshold arithmetic (AGENTS.md gotcha #3).
- [ ] 5.4 Thread it through metadata extraction and remove the global reads at `core/metadata/extractor.py:34`, `keyword.py:16`, `ollama.py:18`, `llamaindex.py:14`, `llamacpp.py:14`.
- [ ] 5.5 Thread it into `core/vectordb/chroma.py`, removing the global reads at `:74` and `:197` in favour of constructor-injected values from `compose.py`.
- [ ] 5.6 Thread it into `integrations/magika.py:25`, `integrations/azure.py:18`, and `integrations/pdf/liteparse.py:45` as call parameters, keeping the ADR-024 lazy Azure import intact.
- [ ] 5.6a Thread it into the four sites group 2's relocation brought into scope, which the original 21-site enumeration predates: `core/codebase/codebase_map.py:19` and `:477`, `core/documents/doc_graph.py:20`, and `core/retrieval/pipeline.py:32` (`from ...config import resolve_sparse_backend, settings` — the `resolve_sparse_backend` half is removed by 7.10). **Ordering:** `codebase_map.py:477` sits in the same block as the ChromaDB leak that task 6.1 rewrites — do 6.1 first, or do both in one edit, so the block is not rewritten twice.
- [ ] 5.7 Delete the module-level `settings = get_settings()` at `config/__init__.py:460` and the `RESOLVED_*` constants; make `compose.py` the only production caller of `get_settings()`.
- [ ] 5.8 Un-`xfail` `tests/test_no_global_settings_reads.py` (task 1.6) and confirm it passes with zero hits.
- [ ] 5.9 Add a test asserting importing `rag_mcp.config` constructs no `Settings` instance (no environment or YAML resolution as an import side effect).

## 6. Restore the ChromaDB and integrations boundaries (F2, F5)

- [ ] 6.1 Replace the direct `import chromadb` / `chromadb.PersistentClient(...)` at `core/codebase/codebase_map.py:476-478` with calls on an injected `VectorStore`; add the needed read method to `core/vectordb/base.py` and implement it in `core/vectordb/chroma.py` if the contract does not already cover it.
- [ ] 6.2 Update `compose.py` and the codebase-map callers in `transports/mcp.py` and `transports/cli/` to pass the constructed store into the codebase map.
- [ ] 6.3 Un-`xfail`/confirm `chromadb-confined-to-vectordb` (task 1.2) now passes; add a test asserting `core/vectordb/chroma.py` is the only `import chromadb` site.
- [ ] 6.4 Delete `import rag_mcp.codebase_map as _cbm` at `integrations/magika.py:81` and the indirection it supports.
- [ ] 6.5 Move the `_is_magika_available` monkeypatch target to `integrations/magika.py` and update every test that patches it on the codebase-map module.
- [ ] 6.6 Confirm `integrations-are-leaves` (task 1.4) now passes.

## 7. Nested configuration schema and YAML migration (F3, F7, F8, F10)

- [ ] 7.1 Rename the redundantly prefixed fields in the subpackage models: `MetadataSettings.metadata_extraction_mode` → `extraction_mode`, `metadata_keyword_rules` → `keyword_rules`, `metadata_taxonomy_mode` → `taxonomy_mode`; `ChunkingSettings.chunk_strategy_fallback` → `strategy_fallback`. Update all consumers.
- [ ] 7.1a Create `IngestionSettings` (design.md D10) as a fourth pure-data subpackage model and move `embed_concurrency` and `embed_batch_size` into it from `ChunkingSettings`, giving `INGESTION__EMBED_CONCURRENCY` / `INGESTION__EMBED_BATCH_SIZE`. Update all consumers, including the group 5.2 threading and the `core/ingestion/_state.py` limiter (8.2).
- [ ] 7.2 Convert `Settings` at `config/__init__.py:186` from `class Settings(ChunkingSettings, RetrievalSettings, MetadataSettings, BaseSettings)` to nested composition with `chunking: ChunkingSettings`, `ingestion: IngestionSettings`, `retrieval: RetrievalSettings`, `metadata: MetadataSettings` and `env_nested_delimiter="__"` in `model_config`.
- [ ] 7.2a Set `extra="forbid"` in the `model_config` of all four subpackage models (design.md D9 layer 1) so any unexpected `CHUNKING__*` / `INGESTION__*` / `RETRIEVAL__*` / `METADATA__*` key fails at resolution naming the offending field. Leave the root `Settings` permissive — it legitimately carries cross-cutting flat keys and unrelated process environment entries. Add tests for both: an unknown nested key raises; an unrelated flat env var does not.
- [ ] 7.3 Rewrite `_YamlDefaultsSource` and `_ProfileYamlSettingsSource` to deep-merge nested mappings instead of flattening SCREAMING_SNAKE keys; keep the precedence chain (defaults < profile < .env < env < explicit) unchanged.
- [ ] 7.4 Rewrite `src/rag_mcp/config/defaults.yaml` into nested blocks: `chunking:` (`chunk_size: 512`, `chunk_overlap: 100`, `markdown_chunk_size: 1024`, `markdown_heading_prepend: false`, `markdown_min_chunk_fraction: 0.0`, `strategy_fallback: markdown`), `ingestion:` (`embed_concurrency: 2`, `embed_batch_size: 100` — per D10, not under `chunking:`), `retrieval:` (`top_k: 10`, `similarity_threshold: 0.0`, `rerank_enabled: false`, `rerank_enabled_for_semantic: true`, `hard_technical_threshold: 0.3`, `rerank_fetch_multiplier: 3`, `rerank_max_fetch: 100`, `hybrid_enabled: false`, `hybrid_rrf_k: 60`, `hybrid_sparse_backend: bm25`), `metadata:` (`extraction_mode: llamaindex`, `taxonomy_mode: category`, `ollama_classify_model: "qwen3:0.6b"`, `ollama_classify_max_attempts: 3`, `ollama_classify_timeout: 30.0`); leave the cross-cutting keys flat and unchanged. Values must be native YAML booleans, not quoted strings.
- [ ] 7.5 Rewrite `src/rag_mcp/config/profiles/documents.yaml` to `retrieval:` (`top_k: 10`, `rerank_enabled: true`, `hybrid_enabled: false`), `chunking:` (`strategy_fallback: markdown`), `metadata:` (`taxonomy_mode: category`), preserving the existing header comments including the ADR-018/ADR-030 reranker rationale.
- [ ] 7.6 Rewrite `src/rag_mcp/config/profiles/codebase.yaml` to `retrieval:` (`top_k: 20`, `rerank_enabled: false`, `hybrid_enabled: true`), `chunking:` (`strategy_fallback: code`), `metadata:` (`taxonomy_mode: file_type`), preserving the Experiment 10 rationale comments.
- [ ] 7.7 Keep `src/rag_mcp/config/profiles/hybrid.yaml` as a selector (`default_profile: documents` only) and add a validator rejecting `retrieval:`/`chunking:`/`ingestion:`/`metadata:` blocks in it. The validator MUST run at `ProfileResolver` construction (equivalently, at settings resolution) — **not** lazily at first collection lookup — so a malformed selector fails at startup rather than at first query. Add a test asserting the failure surfaces during construction with no search performed.
- [ ] 7.8 Search the repository for any other profile YAML (outside `.venv/`) and migrate it to the nested schema in this change; record the inventory in `notes/profile-yaml-inventory.md`.
- [ ] 7.9 Add validation that a bundle using flat SCREAMING_SNAKE keys is rejected with an error naming the offending key, and a test for it.
- [ ] 7.10 Move `resolve_sparse_backend()` (`config/__init__.py:385`) and `resolve_pdf_reader()` (`:412`) plus their `_resolve_*` wrappers into `compose.py`, deleting `from ..core.retrieval.sparse import _detect_native_sparse_capability` at `:395`.
- [ ] 7.11 Move `MAGIKA_LABEL_TO_TREESITTER` (`config/__init__.py:478`) to `core/codebase/code_graph.py` and `SUPPORTED_EXTENSIONS` (`:488`) to `core/ingestion/loader.py`, updating consumers.
- [ ] 7.12 Add the legacy-flat-env-var tripwire (design.md D9 layer 2): a startup validator scanning the process environment for the pre-v2 flat subpackage names and raising a `ValueError` naming the `CHUNKING__*`/`INGESTION__*`/`RETRIEVAL__*`/`METADATA__*` replacement. This covers the case `extra="forbid"` structurally cannot see — a bare `TOP_K` never reaches a subpackage model. Document its lifetime in the module docstring: permanent through v2.x, **removed in v3.0.0** (not v2.1.0 — see D9). Add tests for hit and no-hit paths.
- [ ] 7.13 Confirm `config-is-leaf` (task 1.3) now passes.

## 8. Remove import-time snapshots and split oversized files (F6, F11)

- [ ] 8.1 Delete `MARKDOWN_CHUNK_SIZE = settings.markdown_chunk_size` at `core/ingestion/chunker.py:23`; read the value from the injected settings at the two live consumption points (`:127`, `:188`).
- [ ] 8.2 Delete the import-time `BoundedSemaphore(value=settings.embed_concurrency)` at `core/ingestion/_state.py:22`; construct the limiter at operation start (or in `compose.py`) from the injected concurrency value.
- [ ] 8.3 Add a docstring note on `core/retrieval/reranker.py:43`'s `RERANK_MODEL` recording it as a deliberate compat export per ADR-033:65, consumed by nothing on the live path; add a test asserting no production module reads it.
- [ ] 8.4 Split `core/codebase/code_graph.py` (690) into `code_graph.py` (graph assembly), `ast_extract.py` (tree-sitter extraction), and `communities.py` (deterministic community detection), preserving AGENTS.md invariant #8 (no LLM involvement).
- [ ] 8.5 Split `core/codebase/codebase_map.py` (663) into `codebase_map.py` (assembly), `cache.py` (git-commit-hash-keyed cache, AGENTS.md gotcha #9), and `format.py` (rendering).
- [ ] 8.6 Split `core/documents/doc_graph.py` (562) into `doc_graph.py` and `similarity.py`; split `daemon/watcher.py` (550) into `watcher.py` and `debounce.py`.
- [ ] 8.7 Verify `src/rag_mcp/config/__init__.py` is at or below ~150 lines after groups 5, 7 and 9; split only if it is not.
- [ ] 8.8 Un-`xfail` `tests/test_file_size_ceiling.py` (task 1.5) and confirm zero offenders.

## 9. Delete the v1 compatibility surface (Category A)

- [ ] 9.1 Delete the PEP 562 alias table and `__getattr__` at `config/__init__.py:497-576` (the ~55 legacy constant aliases).
- [ ] 9.2 Delete the nine top-level shim modules: `server.py`, `cli.py`, `watcher.py`, `azure_reader.py`, `ingestion.py`, `retrieval.py`, `metadata_extractor.py`, `reranker.py`, `sparse_retriever.py`.
- [ ] 9.3 Delete the `src/rag_mcp/readers/` package (`__init__.py`, `base.py`, `factory.py`, `pypdf_reader.py`, `pypdfium_reader.py`, `liteparse_reader.py`).
- [ ] 9.4 Update `tests/conftest.py:161`'s `sys.modules.get()` lookup to the `rag_mcp.core.*` path and remove any other test reference to the deleted modules.
- [ ] 9.5 Remove the deprecated-shim entries from `[tool.coverage.run] omit` in `pyproject.toml`, leaving only exclusions that are still justified.
- [ ] 9.6 Verify the packaging surface: `uv run rag-mcp` starts the MCP server and every CLI subcommand runs, with no import of a deleted module.
- [ ] 9.7 Add a one-line note to each archived `experiments/*/run_eval.py` header (or the experiment's `README`) recording that it targets the pre-v2.0.0 import surface and is intentionally not repaired.
- [ ] 9.8 Run `graphify update .` so the knowledge graph reflects the 15 deleted modules before groups 10–13 consult it.

## 10. Complete the enforcement contracts

- [ ] 10.1 Extend the `core-business-avoids-providers-transports` contract's `source_modules` with `rag_mcp.core.vectordb`, `rag_mcp.core.profiles`, `rag_mcp.core.codebase`, `rag_mcp.core.documents`, and `rag_mcp.daemon`; resolve any violation it surfaces.
- [ ] 10.2 Extend `settings-models-are-pure-data` to cover `rag_mcp.core.settings` (the `EffectiveSettings` module).
- [ ] 10.3 Review the `providers-constructed-only-in-compose` contract's `ignore_imports` against the now-lazy registry resolution and tighten or document each exception.
- [ ] 10.3a Remove every `TEMPORARY` `ignore_imports` entry from `chromadb-confined-to-vectordb`, `config-is-leaf` and `integrations-are-leaves` now that groups 5-7 have removed the underlying violations, and confirm the run is clean. All three contracts set `unmatched_ignore_imports_alerting = "error"`, so a stale ignore fails the run — that failure IS the signal that a suppression has outlived its fix. Do not silence it by re-adding the ignore.
- [ ] 10.3b Narrow or document the `integrations.* -> rag_mcp.config` ignores: suppressing that root edge hides **every** chain through `config`, not only the enumerated ones. Record the coverage loss in ADR-037 if it cannot be narrowed.
- [ ] 10.4 Add a test asserting every package under `src/rag_mcp/` appears as a source module in at least one import-linter contract.
- [ ] 10.5 Run `uv run lint-imports` and confirm all contracts pass; record the output in `notes/lint-imports-after.md`.

## 11. Test suite migration

- [ ] 11.1 Migrate every test that patches `rag_mcp.config.settings` attributes to construct an `EffectiveSettings` via the task 4.1 fixture and pass it into the operation.
- [ ] 11.2 Migrate every test that sets a flat subpackage env var (`TOP_K`, `CHUNK_SIZE`, `RERANK_ENABLED`, `METADATA_EXTRACTION_MODE`, `EMBED_CONCURRENCY`, …) to the `RETRIEVAL__*` / `CHUNKING__*` / `INGESTION__*` / `METADATA__*` names. Compare the count migrated against the group 1.1 baseline and record any discrepancy.
- [ ] 11.3 Keep `PDF_READER=pypdf` determinism in the PDF tests (AGENTS.md gotcha #6) and `reset_model_cache()` setup/teardown in the reranker tests (gotcha #2) intact through the migration.
- [ ] 11.4 Add tests for the nested profile bundles: each of `documents` and `codebase` resolves to its documented lever set; a flat-key bundle is rejected; `hybrid.yaml` with a lever block is rejected.
- [ ] 11.5 Add a test that two `search()` calls in one process with different `EffectiveSettings` each honour their own instance (per-collection hybrid mode).
- [ ] 11.6 Add a test that the `documents`/`codebase` profile difference is observable end-to-end through `ProfileResolver` without any global mutation.
- [ ] 11.7 Run the full fast suite and fix any remaining failures.

## 12. Coverage repair

- [ ] 12.1 Re-enable the coverage gate suspended since group 2: run `uv run pytest -m "not slow" --cov=rag_mcp --cov-report=term-missing` and diff each tier against `notes/baseline.md`, attributing every regression to either a real gap or a relocation/split artefact.
- [ ] 12.2 Add tests for the new/split modules (`core/settings.py`, `core/codebase/{cache,format,ast_extract,communities}.py`, `core/documents/similarity.py`, `daemon/debounce.py`) until Core+MCP ≥95%.
- [ ] 12.3 Add tests for `compose.py`'s relocated capability probes (sparse backend `auto`/`native`/`bm25` paths; PDF reader `auto`/explicit/missing-package fallbacks) until Orchestration ≥85%.
- [ ] 12.4 Confirm overall coverage ≥90% and update the coverage tier table in `AGENTS.md` if module paths changed.

## 13. Documentation, ADRs, and the knowledge graph

- [ ] 13.1 Write `docs/adr/037-architecture-v2-conformance.md`: the audit findings closed, the nested configuration schema and its deviation from PROPOSAL §6.2 leaf names, the complete flat → nested environment variable migration table (including `INGESTION__*`), the deletion of the v1 surface, the deliberately broken archived experiments, the v2.0.0 release implication, and the deferred single `layers` import-linter contract.
- [ ] 13.1a Record the two proposal-review resolutions in ADR-037's Decision and Consequences: (a) **D9** — the two-layer config guard, with `extra="forbid"` on the subpackage models as the permanent general-case defence and the enumerated legacy tripwire as a bounded second line whose removal trigger is **v3.0.0**, explicitly not a hypothetical v2.1.0; (b) **D10** — `IngestionSettings` created now rather than deferred, because the breaking rename cost is already paid and deferral would buy a second break. State both as decisions, not open questions.
- [ ] 13.2 Amend ADR-032 to correct its claim that dispatch runs through the strategy registries (true only as of this change) and reference ADR-037.
- [ ] 13.3 Amend ADR-033: correct the Part 2 "no import-time snapshots" claim, note the `RERANK_MODEL` exception at `core/retrieval/reranker.py:43` as deliberate, and repoint the References entry from `src/rag_mcp/server.py` to `transports/mcp.py`.
- [ ] 13.4 Amend ADR-034 to correct "never through ChromaDB APIs directly" (the codebase map bypassed it until this change) and record the new enforcing contract.
- [ ] 13.5 Amend ADR-036: correct §1's "import-linter contracts already cover this" and §3's Magika extraction claim.
- [ ] 13.6 Amend ADR-035 where it describes flat-key profile bundles, pointing at the nested schema.
- [ ] 13.7 Update `docs/brainstorm/refactor-proposal/PROPOSAL.md`: §8 Phase 2's "572 → ~150 lines" to the achieved figure, and §12 to record that the graph-module relocation is complete.
- [ ] 13.8 Rewrite the affected `AGENTS.md` sections: architecture invariants #1–#8 (new `core/codebase/`, `core/documents/` paths; registries as dispatch; settings injected not global), the gotchas list, the module table, and the coverage tier table.
- [ ] 13.9 Update `docs/guides/architecture.md`, `docs/guides/configuration.md` (nested schema, new env var names), `docs/guides/ingestion.md`, `docs/guides/reranker.md`, `docs/guides/cli-reference.md`, and `docs/guides/testing.md` for the injected-settings test pattern.
- [ ] 13.10 Regenerate `.env.example` with the nested variable names and a migration comment block at the top.
- [ ] 13.11 Update `README.md`'s refactor-progress section to state that the v2 conformance work is complete.
- [ ] 13.12 Run `graphify update .` so the knowledge graph reflects the new tree.

## 14. Verification and release

- [ ] 14.1 Run `uv sync` then `uv run pytest -m "not slow" --cov=rag_mcp` and confirm the AGENTS.md floors: Core+MCP ≥95%, Orchestration ≥85%, Overall ≥90%.
- [ ] 14.2 Run `uv run lint-imports` and confirm every contract, including the four new ones, passes.
- [ ] 14.3 Run `openspec validate --all --strict` and fix any reported issue.
- [ ] 14.4 Smoke-test both transports against a scratch collection: `uv run rag-mcp ingest ./docs`, `uv run rag-mcp search "<query>"`, `uv run rag-mcp list`, and an MCP `search_documents` / `get_codebase_map` call; confirm stdout stays clean for MCP (AGENTS.md gotcha #5).
- [ ] 14.5 Verify backward data compatibility: start against an existing `output/chroma_*` directory and confirm collections and their profile metadata tags resolve unchanged.
- [ ] 14.6 Verify the rollback path documented in `design.md`: check out the previous release tag, restore the pre-migration `.env`, and confirm the same ChromaDB data is readable.
- [ ] 14.7 Mirror the task groups into `niftypm/llamaindex-rag-mcp.json` and sync per the `s-niftypm` pipeline.
- [ ] 14.8 Open the PR with a `refactor!:` Conventional Commit title against `main`, confirming `python-semantic-release` will cut **v2.0.0**; never hand-edit `version` in `pyproject.toml`.
- [ ] 14.9 After merge, archive the change with `openspec archive complete-architecture-v2-conformance` and sync `openspec/specs/`.
