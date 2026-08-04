## 1. Preparation

- [x] 1.1 Create branch `git switch -c feat/phase-4-refactor-profiles-dual-use-case` (requires Phases 2 and 3 merged — Phase 2 resolver and Phase 3 store interface are hard prerequisites)
- [x] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate

## 2. Profile bundles

- [x] 2.1 Create `config/profiles/documents.yaml` (markdown fallback, reranker on, top_k=10, dense-only, category taxonomy)
- [x] 2.2 Create `config/profiles/codebase.yaml` (code fallback, reranker off, top_k=20, hybrid+RRF, file_type taxonomy)
- [x] 2.3 Create `config/profiles/hybrid.yaml` declaring `default_profile: documents` (mode selector, not an operational profile with retrieval settings)
- [x] 2.4 Activate the `ProfileYamlSettingsSource` extension point left by Phase 2: insert profile-bundle loading into the precedence chain between `defaults.yaml` and environment sources (deep-merging defaults.yaml + selected profile); add schema validation tests, including a rejection test for an invalid bundle key; verify Phase 2's env-still-wins precedence is preserved

## 3. Profile selection and binding

- [x] 3.1 Add `RAG_PROFILE` env var (`documents` default) to the settings resolver
- [x] 3.2 Implement collection profile tagging via the Phase 3 store interface (`metadata={"profile": "<name>"}` at collection creation; updatable via collection-metadata update)
- [x] 3.3 Implement inheritance: collections with no tag resolve to the server-wide default (test against a pre-refactor collection with no metadata)
- [x] 3.4 Implement hybrid-mode fallback: when `RAG_PROFILE=hybrid`, an untagged collection resolves to `hybrid.yaml`'s `default_profile` (not to `hybrid` itself); test the fallback path
- [x] 3.5 Test: a collection tagged `hybrid` is rejected with a clear error; a collection tagged with a non-existent profile name is rejected listing available profiles

## 4. ProfileResolver and per-operation levers (H1)

- [x] 4.1 Create `core/profiles/resolver.py` with `ProfileResolver.resolve(collection) → EffectiveSettings` (reads collection metadata, loads bundle with cache, applies env overrides)
- [x] 4.2 Classify levers Tier 1 vs Tier 2 per design D1 and pin the classification in tests (embedder/registries/store/reranker-model = Tier 1; reranker toggle, top_k, hybrid, chunking fallback, taxonomy = Tier 2)
- [x] 4.3 Thread resolved levers as parameters through `search()` — no global reads for Tier 2 levers in `core/`
- [x] 4.4 Thread resolved levers as parameters through `ingest_path_async()` (chunking fallback + taxonomy mode)
- [x] 4.5 Test: one process serving a `documents` collection (rerank applied) and a `codebase` collection (rerank skipped) with the reranker model loaded at most once

## 5. Non-destructive profile changes and safety contract (M6)

- [x] 5.1 Implement the safety-contract generator (chunk count, old → new profile, per-lever impact statements, `--force` re-ingest pointer)
- [x] 5.2 CLI transport: interactive `Continue? [y/N]` prompt; aborts on `N`
- [x] 5.3 MCP transport: profile-change tool returns `{"status": "preview", "contract": ..., "confirm_required": true}` and mutates only on re-invocation with `confirm=True`
- [x] 5.4 Test: confirmed profile change on a non-empty collection leaves chunk count, embeddings, and content byte-identical; query-time levers apply immediately
- [x] 5.5 Test: content-type dispatch still wins over profile strategy for known types (`.py` → code strategy in a documents-profile collection)

## 6. Revalidation, docs, and acceptance (M1)

- [x] 6.1 Revalidate the documents-profile `reranker_enabled: true` flip against Experiment 10's findings; record the outcome in ADR-035; the evidence supports the split (Experiment 10 evaluated technical workloads, not document grounding)
- [x] 6.2 Correct AGENTS.md invariant #5 (stale `RERANK_ENABLED=true` claim) to state the true code default and the profile-level restoration
- [x] 6.3 Write ADR 035 (Profiles: Dual Use Cases) covering bundles, collection binding, two-tier resolution, and non-destructive changes
- [x] 6.4 Update `docs/guides/configuration.md` with the profiles section (bundles, `RAG_PROFILE`, precedence)
- [ ] 6.5 Run `uv run pytest -m "not slow" --cov=rag_mcp` — green, coverage thresholds hold
- [ ] 6.6 Run `openspec validate phase-4-refactor-profiles-dual-use-case --strict`
- [ ] 6.7 Run `graphify update .`
- [ ] 6.8 Commit (`feat:` — new user-facing capability) and open PR with `gh pr create --base main`
