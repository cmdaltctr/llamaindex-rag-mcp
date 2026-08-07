## 1. Retirement lifetime policy

- [x] 1.1 Rewrite the module docstring of `src/rag_mcp/config/legacy.py` to state
      the shape-aware rule (design.md D1/D2): nested entries expire one major
      after retirement; flat entries persist while an upgrade path exists from a
      version that read them. State the rule without naming a current version.
- [x] 1.2 Replace the "LIFETIME: … removed in v3.0.0" comment block with a
      reference to the rule, and annotate the two groups in `_RETIRED_ENV_VARS`
      (flat / nested) so the applicable lifetime is readable at the dict.
- [x] 1.3 Record in the docstring *why* flat entries are retained — pydantic
      cannot detect them (D1's measurement) — so the retention is not "cleaned
      up" by a future reader without re-deriving it.
- [x] 1.4 Update CLAUDE.md gotcha #11 to reference the rule instead of restating
      the v3.0.0 trigger.
- [x] 1.5 Append a dated forward-note (2026-08-07) to
      `docs/adr/037-architecture-v2-conformance.md` recording that the v3.0.0
      removal trigger is superseded by the shape-aware rule. Do not edit the
      decision text — match the forward-note style already used in that file.

## 2. Retirement guard test

- [x] 2.1 Add `tests/test_docs_no_retired_env_vars.py`. Import
      `_RETIRED_ENV_VARS` from `rag_mcp.config.legacy` so the test cannot drift
      from the real mapping.
- [x] 2.2 Scan operator-facing paths only: `.env.example`, `README.md`, and
      every `.md` under `docs/guides/`. Scan by directory, not an enumerated
      file list, so new guides are covered automatically (design.md Risks).
- [x] 2.3 Match assignment form `^\s*#?\s*NAME=` per line, where `NAME` is a key
      of `_RETIRED_ENV_VARS`. Include the commented form — `.env.example`
      teaches by commented assignment, so `# TOP_K=10` is equally misleading.
- [x] 2.4 On failure, report file, line number, the retired name, and its
      replacement. Assert the test currently fails with exactly one finding at
      `docs/guides/getting-started.md:54` before fixing 3.1 — this proves the
      test detects the real bug rather than passing vacuously.
- [x] 2.5 Add a negative case asserting prose mentions do not trip the check
      (e.g. the migration sentence at `README.md:208`), pinning the
      assignment-vs-mention distinction that makes the test survivable.

## 3. Documentation corrections

- [x] 3.1 Fix `docs/guides/getting-started.md:54`: `RERANK_ENABLED=true` becomes
      `RETRIEVAL__RERANK_ENABLED=true`. Touch only this line — the incorrect
      "enabled by default" claim on line 49 belongs to `doc-rot-sweep`.
- [x] 3.2 Confirm task 2 now passes with zero findings.
- [x] 3.3 Update the 10 living `openspec/specs/*.md` files that name flat
      variables in requirement text to the nested names:
      `async-ingestion`, `cloud-embed-providers`, `config-composition-root`,
      `hybrid-retrieval`, `inference-backend`, `markdown-aware-chunking`,
      `metadata-extraction`, `modular-core-extraction`, `reranking`,
      `profiles-dual-use-case`, `semantic-technical-reranker-policy`. Verify the
      list against `grep` before editing; do not touch `openspec/changes/archive/`.
- [x] 3.4 Update `tests/TEST_README.md` where it names flat variables.

## 4. OpenRouter extraction backend

- [x] 4.1 Create `src/rag_mcp/core/metadata/openrouter.py` and move
      `_extract_openrouter_chat_async` into it from `extractor.py`, unchanged.
      Include `from __future__ import annotations` and Google-style docstrings.
- [x] 4.2 Update `core/metadata/registry.py:67` to register `openrouter` against
      the new module path.
- [x] 4.3 Move the `_extract_openrouter_chat_async` entry in the PEP 562
      `_NAMES` map in `core/metadata/__init__.py` from `.extractor` to
      `.openrouter`.
- [x] 4.4 Update patch targets in `tests/test_metadata_extractor.py` — the
      `TestOpenRouterStructuredOutputDowngrade` cases patch
      `_extract_openrouter_chat_async` and `_retry_sleep` relative to
      `extractor`. Patching the re-exporting module is a silent no-op
      (CLAUDE.md gotcha 8b), so verify each patch actually binds.
- [x] 4.5 Run the OpenRouter tests specifically and compare the passed count to
      the pre-move baseline. An equal count with a broken patch target would
      still be green — confirm the tests fail when the implementation is
      deliberately broken.
- [x] 4.6 Tasks 4.1-4.4 land in a single commit; the intermediate state has
      tests that pass without exercising the code.

## 5. OpenRouter LLM provider

- [x] 5.1 Create `src/rag_mcp/core/providers/llm/openrouter.py` with a `build`
      function matching the signature of the `ollama` and `llamacpp` providers.
      Move the endpoint `https://openrouter.ai/api/v1` into it from the inline
      literal.
- [x] 5.2 Add the `register("openrouter", …)` line to
      `core/providers/llm/registry.py`.
- [x] 5.3 Replace the inline `OpenAILike(...)` construction at
      `core/metadata/llamaindex.py:179-184` with a registry lookup. Preserve the
      existing `ImportError` fallback-to-local behaviour and its warning.
- [x] 5.4 Delete `_CLOUD_BACKENDS = {"openrouter": "openrouter"}` from
      `extractor.py:78` together with its single caller at `extractor.py:57`.
- [x] 5.5 Confirm the config surface is unchanged — `openrouter_llm_model`,
      `openrouter_api_key`, `cloud_backend` keep their names and meanings. If
      anything shifts, stop and mark the change BREAKING in proposal.md.

## 6. Symmetry test

- [x] 6.1 Add a test enumerating both registries and asserting `ollama`,
      `llamacpp`, and `openrouter` appear in each under the same name.
- [x] 6.2 Assert no entry in the metadata extraction registry resolves to the
      dispatch module `core.metadata.extractor`.
- [x] 6.3 Assert every sub-provider name accepted by config validation
      (`config/__init__.py:159,171`) is registered, so a selectable-but-missing
      provider fails loudly.

## 7. Validation

- [ ] 7.1 `uv run pytest -m "not slow" -v` — all pass, count at or above the
      pre-change baseline.
- [ ] 7.2 `uv run lint-imports` — 6 contracts kept, 0 broken. Delete any
      `ignore_imports` entry made stale by the moves; a stale entry fails the
      build by design (gotcha 8c).
- [ ] 7.3 `uv run pytest --cov=rag_mcp` — coverage at or above 90% overall, and
      `core/metadata` at or above its 95% tier.
- [ ] 7.4 Confirm no file exceeds 500 lines (`tests/test_file_size_ceiling.py`);
      `extractor.py` should shrink.
- [ ] 7.5 `uv run openspec validate --all --strict`.

## 8. Post-release (do not run before v3.0.0 ships)

- [ ] 8.1 Once v3.0.0 is released, delete the two nested classify entries
      (`METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS`,
      `METADATA__OLLAMA_CLASSIFY_TIMEOUT`) from `_RETIRED_ENV_VARS` — they are
      the migration path *into* v3 and must survive the release itself.
- [ ] 8.2 Update the mapping pin in `tests/test_config_no_legacy_surface.py` to
      the reduced set.
- [ ] 8.3 Confirm both names still fail startup after deletion, via block
      `extra="forbid"` (design.md D1) — the failure survives, only the message
      degrades.
