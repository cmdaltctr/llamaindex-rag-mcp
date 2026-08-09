## 1. Re-verify the rot before editing

Line numbers below were verified on 2026-08-07 against branch
`feat/rename-classify-settings` @ `7f26ee4`. They shift if any earlier task
edits the same file, so re-anchor by content, not by number.

- [x] 1.1 Confirm the registry names are still absent from `src/`:
      `grep -rn "LOCAL_LLM_PROVIDERS\|CLOUD_LLM_PROVIDERS\|LOCAL_EMBED_PROVIDERS\|CLOUD_EMBED_PROVIDERS" src/`
      → MUST return nothing. If it returns hits, stop: the premise has changed.
- [x] 1.2 Confirm the live registrations, which the rewrite in §3 must match:
      `grep -n "^register(" src/rag_mcp/core/providers/embeddings/registry.py src/rag_mcp/core/providers/llm/registry.py src/rag_mcp/core/metadata/registry.py`
      → expect embeddings `ollama, llamacpp, openrouter`; llm `ollama, llamacpp`;
      metadata `keyword, ollama, llamacpp, llamaindex, openrouter`.
- [x] 1.3 Confirm the reranker default is still `False`:
      `grep -n "rerank_enabled" src/rag_mcp/core/retrieval/settings.py`
      → expect `rerank_enabled: LegacyBool = False` (~line 49).
- [x] 1.4 Confirm `_dispatch_local_extraction` still dispatches via the registry
      and not `if/elif` (`src/rag_mcp/core/metadata/extractor.py:61`). This is
      what makes the ADR gap "closed" rather than "still open".

## 2. ADR forward notes (append only — never edit decision text)

- [x] 2.1 `docs/adr/026-provider-registry-and-openrouter.md` — append a
      `## Update (2026-08-07, doc-rot-sweep)` section **at end of file**
      (currently 168 lines), below the existing `## Update (2026-08-04, Phase 2)`
      at line 134. Do **not** modify the Phase 2 note. The new note records:
      - The nested dicts named in Decision (line ~46-53) were **replaced**, not
        relocated. Phase 2's note said "physically relocated" with names intact;
        that is no longer accurate. Today: five flat per-domain registries using
        `register(name, "module:attr")`, listed in §1.2.
      - The **known gap is closed.** Consequence at line 104 ("LLM registries
        are not yet wired… `metadata_extractor.py` still uses if/elif dispatch")
        no longer holds: LLM selection resolves through
        `core/metadata/registry.py`. Phase 2's claim that "the LLM dispatch path
        itself was not rewritten in this phase" is superseded.
      - Consequence at line 106 ("Cloud dispatch hardcodes `openrouter` …
        without checking `CLOUD_BACKEND`") is **also closed** —
        `_local_strategy_name()` reads `settings.cloud_backend`.
      - Reference at line 127 (`src/rag_mcp/config.py`) and line 128
        (`src/rag_mcp/metadata_extractor.py`) are v1 paths deleted in v2.0.0;
        name the current locations. Leave the lines themselves in place.
- [x] 2.2 `docs/adr/027-local-cloud-provider-naming.md` — insert an inline
      blockquote note directly **after line 67** (the "LLM registries not yet
      fully wired" bullet), in the established form
      `> **Update (doc-rot-sweep, 2026-08-07):** …`, recording that the
      follow-up condition it set ("when a second LLM sub-provider is added") was
      met and the registry migration is done.
- [x] 2.3 `docs/adr/027-local-cloud-provider-naming.md` — add a second inline
      note after the References bullet at line 89, redirecting
      `src/rag_mcp/config.py` to `core/providers/{embeddings,llm}/registry.py`
      and noting `_build_provider()` no longer exists (construction now lives in
      `compose.py` as `build_embed_model` / `build_llm_model`).
- [x] 2.4 Verify no decision text changed: `git diff docs/adr/` MUST show
      additions only (no `-` lines other than trailing-whitespace normalisation).

## 3. Rewrite the providers guide registry section

- [x] 3.1 `docs/guides/providers.md` — replace lines **110–126** (`## Registry
      pattern` through the "No changes to `ingestion.py`…" paragraph) with an
      accurate description:
      - Registries live in `core/providers/embeddings/registry.py`,
        `core/providers/llm/registry.py`, `core/metadata/registry.py`.
      - Each maps a name to a `"module:attr"` import string, resolved and cached
        on first `get()`; importing a registry imports no provider module, so a
        missing optional dependency degrades gracefully.
      - Construction happens in `compose.py` (`build_embed_model`,
        `build_llm_model`), enforced by `import-linter`.
      - Drop all four `LOCAL_*`/`CLOUD_*` names and `_build_provider`.
- [x] 3.2 Rewrite the "Adding a new provider" steps. Correct procedure:
      (1) add `core/providers/<kind>/<name>.py` exposing `build(settings)`;
      (2) add one `register("<name>", "rag_mcp.core.providers.<kind>.<name>:build")`
      line at the bottom of that registry;
      (3) add the optional-dependency extra in `pyproject.toml` and, if it is an
      extra, an entry in `_PROVIDER_EXTRAS` (`providers/llm/registry.py:31`);
      (4) add env vars to `.env.example`;
      (5) add the name to the delimited block from task 4.3;
      (6) tests. Note the old step-4 target `tests/unit/test_provider_config.py`
      does not exist — point at `tests/test_registry_contract.py`.
- [x] 3.3 Confirm no dangling path remains:
      `grep -n "src/rag_mcp/config\.py" docs/guides/providers.md` → nothing.
- [x] 3.4 Leave the "Shared classification knobs" blockquote (lines 103–108)
      **untouched** — it is accurate post-rename and its env-var names belong to
      `tripwire-retirement-and-provider-symmetry`.

## 4. Fix the factual errors

- [x] 4.1 `docs/guides/getting-started.md:50` — replace "The reranker is enabled
      by default and significantly improves search precision" with the truth: it
      is **off by default**; Experiment 10 measured a 19–27% degradation on
      technical/code workloads, so it is opt-in, and the `documents` profile
      turns it on while `codebase` leaves it off. Cite ADR-018 and Experiment 10.
      **Scope guard:** edit the prose sentence only. Do **not** touch the fenced
      `RERANK_ENABLED=true` block at lines 52–54 — the env-var *name* fix is
      owned by `tripwire-retirement-and-provider-symmetry`.
- [x] 4.2 `tests/TEST_README.md` — replace item 3 (lines **92–98**, "Module-level
      constants patched via `sys.modules`") with the ADR-037 reality: there is no
      singleton to patch; tests use the `effective_settings(**overrides)`
      conftest factory or `set_default_effective_settings(...)`, and the conftest
      default sets `extraction_mode="disabled"` and `pdf_reader="pypdf"`.
      Cross-check against CLAUDE.md gotcha 8a so the two agree.
- [x] 4.3 `docs/guides/providers.md` — add the machine-readable provider block
      that task 5.2 asserts against, e.g. delimited by
      `<!-- registry-names:embeddings -->` / `<!-- /registry-names -->` and
      `<!-- registry-names:llm -->` / `<!-- /registry-names -->`, each wrapping
      the visible list of names. Keep it human-readable — it is documentation
      first and a test fixture second.

## 5. Prevention (see design.md Decision 4 for why these two and not a linter)

- [x] 5.1 Add `tests/test_docs_references.py`: scan `docs/guides/**/*.md` and
      `tests/TEST_README.md` for `src/rag_mcp/...py` paths; assert each exists.
      Exclude `docs/adr/` — historical records legitimately cite moved paths
      (spec scenario 2). Failure message MUST name file, line, and path.
      Expect exactly one failure before task 3.1 lands and zero after.
- [x] 5.2 Extend `tests/test_registry_contract.py` with
      `test_documented_provider_names_match_registries`: parse the delimited
      blocks from task 4.3 and assert set-equality against
      `embed_registry.available()` and `llm_registry.available()`. The file
      already imports both registries at module scope. Failure message MUST name
      the differing provider and the direction (documented-not-registered vs
      registered-not-documented).
- [x] 5.3 Add a standing item to the change/ADR checklist: when a default value
      changes, grep `docs/guides/` for the old value. Record in design.md
      Decision 5 terms — a procedural partial, not automation.
- [x] 5.4 Sanity-check that 5.1 and 5.2 actually fail on the rot: stash the §3–§4
      fixes, run both tests, confirm red; restore, confirm green. A prevention
      test never observed failing is not a prevention test.

## 6. Validate

- [x] 6.1 `uv run openspec validate --all --strict`
- [x] 6.2 `uv run pytest tests/test_docs_references.py tests/test_registry_contract.py -v`
- [x] 6.3 `uv run pytest -m "not slow" --cov=rag_mcp` — confirm coverage floors
      hold. No `src/` change, so no coverage movement is expected; investigate
      any.
- [x] 6.4 Re-run the §1 greps to confirm the docs now match the code.
- [x] 6.5 Confirm the boundary held: `git diff` MUST NOT touch
      `src/rag_mcp/config/legacy.py`, any env-var name, or
      `openspec/specs/metadata-extraction/spec.md` (deferred to
      `tripwire-retirement-and-provider-symmetry`).
