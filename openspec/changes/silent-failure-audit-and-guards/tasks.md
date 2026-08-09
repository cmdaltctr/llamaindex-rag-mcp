## Delivery sequence (two PRs off v3)

This change ships as **two PRs split along the breaking line** (design.md Migration Plan: Phase 2 non-breaking, Phase 3 breaking). The split is load-bearing: PR1 merges on normal review; PR2 is BREAKING and banks a major bump. Read this before implementing — it fixes commit grouping, which tasks share a commit, and when to merge and archive.

Branch state: you are on `v3`. `v3` is the breaking-accumulation branch; `semantic-release` fires on `main`, so commits on `v3` do not release until the eventual `v3`→`main` merge. Open both PRs with `--base v3`, never `--base main`.

### PR 1 — non-breaking: reranker guards

Carries: proposal artifacts + §1-§4 + the `reranking` and `score-normalisation` delta specs + docs 8.1/8.2.

1. `git fetch origin v3 && git switch -c fix/silent-failure-reranker-guards origin/v3` (the untracked `openspec/changes/silent-failure-audit-and-guards/` dir follows the switch; no stash).
2. Commit the plan first as `docs(openspec): propose silent-failure audit and guards` — `proposal.md`, `design.md`, `tasks.md`, all four `specs/` deltas. Reviewers see the plan alongside the first code.
3. Implement §1-§4 (reranker escalation, diagnostics reason, threshold-outcome fix, CoreML tests) plus the `reranking` + `score-normalisation` delta specs plus docs 8.1 (ADR-029 Resolved-by note) and 8.2 (reranker.md). Commit as `fix:` (closes ADR-029 decision #3; non-breaking).
4. Gate: `openspec validate silent-failure-audit-and-guards --strict`, `uv run pytest -m "not slow" --cov=rag_mcp`, `uv run --no-sync lint-imports`. Confirm `core/retrieval` stays ≥95%.
5. `gh pr create --base v3`. Merge on normal review (merge commit, delete branch).

### Between PRs

After PR1 merges, branch PR2 from updated `v3` so it includes the reranker code its docs (8.1/8.2) reference: `git fetch origin v3 && git switch -c fix/silent-failure-config-fail-fast origin/v3`.

### PR 2 — breaking: config fail-fast

Carries: §5-§7 + the `config-composition-root` and `inference-backend` delta specs + docs 8.3/8.5 + filing 8.4/8.6. **Two atomic commits inside this PR** — the bisect rule is the reason.

**Commit A — §5 + its test rewrite (atomic).** §5 removes the `try/except` in `ensure_runtime_setup`; `test_ensure_runtime_setup_degrades_gracefully` asserts the swallow and goes red the instant §5 lands. Rewrite it to `pytest.raises` (task 7.1) in this same commit.

**Commit B — §6 raises + §7 test retirement (atomic).** §6 makes six provider settings raise; the §6 red set is 11 failures across 4 modules (measured, §7). Retire/rewrite them (tasks 7.2-7.6) in the same commit as the §6 raises.

Then further commits: the `config-composition-root` + `inference-backend` delta specs, docs 8.3 (configuration.md migration note) and 8.5 (doc-rot grep), and the filed 8.4/8.6 follow-up proposals.

**Commit type decides the bump.** The breaking commit (Commit B) MUST be `fix(config)!:` with a `BREAKING CHANGE:` footer naming the six env vars. The `!` plus footer is what `semantic-release` turns into a major at the `v3`→`main` merge; omit it and a change that fails startup on existing configs ships as a patch.

Gate before opening: same triple (`openspec validate --strict`, `pytest --cov`, `lint-imports`). Confirm `config/` stays ≥95%. `gh pr create --base v3`.

### Archive (after PR2)

The change stays open across both PRs with tasks.md ticked progressively. Archive only after PR2 merges AND tasks 8.4 (module-scope refactor proposal) and 8.6 (`_resolve_active_strategies` proposal) are filed — both must exist as opened changes before this one can close.

## 1. Reranker persistent-failure escalation (`core/retrieval/reranker.py`)

- [ ] 1.1 Add a module-level `_FAILURE_STATE` holding a single process-wide consecutive-failure count plus the last error signature, guarded by the existing `_CACHE_LOCK`, sibling to `_MODEL_CACHE`. It MUST NOT be instance state (a fresh reranker is built per `search()` call, so the counter would never increment) and MUST NOT live inside `_MODEL_CACHE` (that dict is written only on successful load, so a permanently failing model has no entry). Single count, not keyed by model ID — see design.md for the split-counter trap.
- [ ] 1.2 Define the escalation threshold as a named module-level constant (3 consecutive failures) — not an env var (design.md: premature configurability).
- [ ] 1.3 Add a shared helper that records a failure: compare the new error's signature against the stored one, increment or reset, and return the log level to use (WARNING below threshold, ERROR at or above).
- [ ] 1.4 Wire the helper into `rerank()`'s inference `except Exception` handler (the ADR-029 CoreML shape).
- [ ] 1.5 Wire the helper into `_load_model()`'s `except Exception` handler. Because `_load_model` retries on every call, a permanently bad model ID is the other half of the "warning on every call, invisible" pattern — covering only 1.4 would leave it untouched.
- [ ] 1.6 Reset the counter on any successful load or successful inference.
- [ ] 1.7 Extend `reset_model_cache()` to clear `_FAILURE_STATE` so no count leaks across test cases.
- [ ] 1.8 Test: a single failure logs WARNING and falls back gracefully, `tests/test_reranker.py`.
- [ ] 1.9 Test: the same error signature repeated to the threshold escalates to ERROR (assert via `caplog`), `tests/test_reranker.py`.
- [ ] 1.10 Test: a success between failures resets the counter — the next failure logs WARNING, not ERROR.
- [ ] 1.11 **Test through the un-injected path**: drive `search()` with `reranker=None` so a fresh instance is constructed per call, and assert escalation still fires. The existing `TestPersistentRerankFailureFallback` injects a single instance via DI, so a test written in that style would pass while production never escalates — the exact ADR-029 trap. This test is what proves the counter survives instance churn.
- [ ] 1.12 Test: `reset_model_cache()` clears the counter, `tests/test_reranker.py`.
- [ ] 1.13 Fix the pre-existing cache leak in `tests/test_retrieval.py::test_transient_failure_retries_then_succeeds` — it populates `_MODEL_CACHE` via `_load_model()` without calling `reset_model_cache()`. Harmless today; load-bearing once `_FAILURE_STATE` shares the same reset hook.

## 2. Reranker failure reason in diagnostics (`core/retrieval/reranker.py`, `core/retrieval/pipeline.py`)

- [ ] 2.1 Record the failure on the reranker instance (e.g. `self.last_failure_reason`), set in both failure handlers and cleared on success.
- [ ] 2.2 In `search()`, after the `rerank()` call, read it back with `getattr` and override the policy-derived `rerank_reason` when present. Required because `search` currently assigns `rerank_reason` unconditionally from the policy resolver *after* reranking, clobbering anything the reranker wrote into the result dicts.
- [ ] 2.3 Test: `search(..., rerank=True, include_diagnostics=True)` with a failing reranker returns a `rerank_reason` describing the failure, not the policy string.
- [ ] 2.4 Test: `include_diagnostics=False` (default) result shape is unchanged — no new keys leak into the public result dict.

## 3. Threshold scaling follows rerank outcome (`core/retrieval/pipeline.py`, `core/retrieval/policy.py`)

- [ ] 3.1 Change the `_effective_threshold` call site to pass whether reranking actually *succeeded* (derivable from the `reranked` flag already propagated onto results) rather than `effective_rerank`, which is only the request. Leave the ÷30 factor itself unchanged — it is calibrated (CLAUDE.md gotcha #3).
- [ ] 3.2 Test: successful reranking still applies the ÷30-scaled threshold (regression guard on existing `TestThresholdScaling`).
- [ ] 3.3 Test: a failed reranker with `rerank=True` applies the **unscaled** threshold, so un-reranked cosine scores are filtered at the value the caller asked for.
- [ ] 3.4 Test: `rerank=False` applies the unscaled threshold (unchanged behaviour).

## 4. RERANK_ONNX_PROVIDER=coreml guard test coverage (`core/retrieval/reranker.py`)

- [ ] 4.1 Test: `RERANK_ONNX_PROVIDER` unset → ONNX session constructed with `["CPUExecutionProvider"]` only.
- [ ] 4.2 Test: `RERANK_ONNX_PROVIDER=coreml` with `CoreMLExecutionProvider` mocked into `ort.get_available_providers()` → session constructed with `["CoreMLExecutionProvider", "CPUExecutionProvider"]`.
- [ ] 4.3 Test: `RERANK_ONNX_PROVIDER=coreml` with `CoreMLExecutionProvider` NOT available → session falls back to `["CPUExecutionProvider"]` only, no error.

## 5. Composition root fails fast on construction errors (`compose.py::ensure_runtime_setup`)

- [ ] 5.1 Remove the `try/except (ImportError, ValueError)` around `build_embed_model` — let the exception propagate.
- [ ] 5.2 Remove the `try/except (ImportError, ValueError)` around `build_vector_store` — let the exception propagate.
- [ ] 5.3 Do **not** move the module-scope `ensure_runtime_setup()` call or add entry-point wrapping. Import-time failure is the accepted, consistent-with-`VECTOR_STORE` behaviour for this change (design.md); the move is filed separately in 8.4.
- [ ] 5.4 Test: `build_embed_model` raising `ValueError`/`ImportError` propagates out of `ensure_runtime_setup`, `tests/test_compose.py`.
- [ ] 5.5 Test: `build_vector_store` raising `ValueError`/`ImportError` propagates out of `ensure_runtime_setup`, `tests/test_compose.py`.
- [ ] 5.6 Test: pytest **collection** succeeds under the `tests/conftest.py` provider defaults (`EMBED_PROVIDER=local`, `LOCAL_BACKEND=ollama`, `EMBED_MODEL` set via `setdefault` before any import). This is the specific thing that would silently rot once construction failures propagate at import.
- [ ] 5.7 Test: the successful construction path is unchanged (regression check on `test_ensure_runtime_setup_assigns_embed_model_once`).

## 6. Provider-selection validation fails fast (`config/__init__.py`)

- [ ] 6.1 Move `_validate_provider_selections` **above** `_validate_embed_model_required` in the class body. Pydantic runs `mode="after"` validators in definition order, and `_validate_embed_model_required` currently resolves an unknown provider to `local_backend` and raises about a missing `EMBED_MODEL` — so a bad `EMBED_PROVIDER` would report the wrong setting, and task 6.9's assertion would pass or fail depending on ambient env.
- [ ] 6.2 Change the `EMBED_PROVIDER` unknown-value branch from `logger.warning` + clamp to `raise ValueError(...)` naming the value and the accepted set. Accepted set is `local`, `cloud`, `ollama`, `llamacpp`, `openrouter` — the code's set, not the spec's stale one.
- [ ] 6.3 Change the `METADATA_LLM_PROVIDER` unknown-value branch to raise (accepted: `local`, `cloud`).
- [ ] 6.4 Change the `LOCAL_BACKEND` unknown-value branch to raise (accepted: `llamacpp`, `ollama`).
- [ ] 6.5 Change the `CLOUD_BACKEND` unknown-value branch to raise (accepted: `openrouter`).
- [ ] 6.6 Change the `RETRIEVAL__HYBRID_SPARSE_BACKEND` unknown-value branch to raise (accepted: `auto`, `native`, `bm25`) — do not touch the separate `native`-requested-but-unsupported capability fallback, which is a different code path under the `hybrid-retrieval` capability and stays as-is.
- [ ] 6.7 Change the `DOCUMENT_BACKEND` unrecognised-value branch (not in `("local", "azure")`) to raise — leave the `DOCUMENT_BACKEND=azure` + missing-credentials branch exactly as is (warn + fall back to local).
- [ ] 6.8 Leave the `RAG_PROFILE` unknown-value branch unchanged (warn + fall back to `documents`); add a comment cross-referencing this decision so a future audit does not re-flag it.
- [ ] 6.9 **Implement empty/whitespace handling.** The prototype surfaced `RETRIEVAL__HYBRID_SPARSE_BACKEND=""` as an existing parametrised case that clamps to `bm25` today and would raise after this change. An empty `.env` value (`SETTING=`) is how operators unset a knob, so raising on it is hostile. Rule for all six settings: strip the value; if empty after strip, reset the field to its declared default; otherwise test the stripped value against the accepted set, store the stripped value, and raise only on a non-empty unrecognised value. Two points are load-bearing. (1) Resetting to the default means `object.__setattr__(self, field, type(self).model_fields[field].default)` inside the validator, not merely skipping the raise. Skipping leaves `""` in the field, which reaches runtime: `resolve_sparse_backend` would probe `native` on `""` and log a spurious fallback instead of behaving as unset. (2) The strip must feed the membership test. Today `" auto "` is not in `("auto","native","bm25")` and silently clamps to `bm25`; without a strip this change converts it into a raise, the same hostility. All six field defaults equal their current clamp targets, so resetting empty to the default preserves today's empty-value result.
- [ ] 6.10 Test: an empty value for each of the six settings resolves to the field default and does NOT raise; a whitespace-padded valid value (e.g. `" auto "`) resolves to the stripped value, not a raise and not the clamp.
- [ ] 6.11 Test: each of the six raising branches raises with the offending value in the message, `tests/unit/test_provider_config.py`.
- [ ] 6.12 Test: `EMBED_PROVIDER=bogus` + `LOCAL_BACKEND=ollama` + `EMBED_MODEL` unset raises naming `EMBED_PROVIDER`, not `EMBED_MODEL` (guards the 6.1 ordering).
- [ ] 6.13 Test: `DOCUMENT_BACKEND=azure` with missing credentials still warns and falls back to local (regression guard for the boundary this change must not cross).
- [ ] 6.14 Test: `RAG_PROFILE` unrecognised value still warns and falls back to `documents` (regression guard).
- [ ] 6.15 Test: `VECTOR_STORE` and `PDF_READER` unknown-value behaviour is unchanged (regression guard — confirms adjacent branches were not touched).

## 7. Retire or rewrite tests that assert the removed behaviour

§6 was prototyped against the working tree and `uv run pytest -m "not slow"` was run, giving `11 failed, 1095 passed, 1 skipped` across **4 modules**. Collection succeeded and no unrelated module cascaded, which also empirically confirms task 5.6's assumption.

§5 was **not** in that prototype run. 7.1 below was found by reading the test, not by running it: `tests/test_compose.py::test_ensure_runtime_setup_degrades_gracefully` patches `build_embed_model` to raise and asserts `# must not raise`, so it goes red the moment §5 removes the guard. Before trusting this list is complete, measure §5 the same way (apply only §5, run the suite, record the count).

- [ ] 7.1 `tests/test_compose.py::test_ensure_runtime_setup_degrades_gracefully` — asserts the §5 swallow (`# must not raise`). Rewrite to `pytest.raises`. **Must land in the same commit as §5.1-5.2** (PR2 Commit A, see Delivery sequence) — if §5's code and this rewrite are separate commits the branch is red in between and bisect breaks.
- [ ] 7.2 `tests/test_sparse_backend_fallback.py` — **7 failures**: `test_invalid_backend_falls_back_to_bm25` (parametrised over `total_nonsense`, `BM25`, `""`, `sparse`, `none`), plus `test_clamp_does_not_create_a_root_attribute` and `test_warning_names_the_nested_variable`. Retire the module: those last two are the regression guard for a recently-fixed bug in the clamp's write target, and removing the clamp deletes the code path that bug lived in. Record that rationale in the commit message so the deletion is a decision, not collateral. The `""` and whitespace cases are now covered by task 6.9's reset-to-default rule, not by this clamp.
- [ ] 7.3 `tests/test_compose.py::test_build_embed_model_validates_unknown_provider` — asserts `embed_provider == "local"` and `local_backend == "llamacpp"` after passing `"bogus"`. Rewrite to `pytest.raises`.
- [ ] 7.4 `tests/test_settings_resolver.py::test_cloud_backend_invalid_value_clamped_to_openrouter` — asserts the `CLOUD_BACKEND` clamp. Rewrite to `pytest.raises`. (Found only by running the suite; missed by reading assertions.)
- [ ] 7.5 `tests/unit/test_provider_config.py::test_unknown_embed_provider_falls_back_to_local` — rewrite to `pytest.raises`.
- [ ] 7.6 `tests/unit/test_provider_config.py::test_unknown_local_backend_falls_back_to_llamacpp` — rewrite to `pytest.raises`.
- [ ] 7.7 Tasks 7.2-7.6 (the §6 red set) **must land in the same commit as the §6 raises** (PR2 Commit B). Re-run `uv run pytest -m "not slow"` after 7.1-7.6 and confirm the suite is green. The §6 count is measured; the §5 count (7.1) must be confirmed by the §5 measurement above before this task can pass.

## 8. Documentation and follow-up

- [ ] 8.1 Add a "Resolved by" note to `docs/adr/029-disable-coreml-for-reranker-silent-fallback-lesson.md` closing decision #3's refactor reminder. It MUST state that bullet 3's "log at ERROR, not WARNING" shipped as *thresholded* escalation, not unconditional ERROR, and why (design.md) — so a later reader does not assume it shipped verbatim.
- [ ] 8.2 Update `docs/guides/reranker.md` — the escalation threshold, the `rerank_reason` diagnostic, and the corrected threshold-scaling condition (its "Threshold auto-scaling" and "Fallback" sections both describe current behaviour that changes here).
- [ ] 8.3 Update `docs/guides/configuration.md` — the six env vars that now fail startup on an unrecognised value, their accepted sets, and a migration note for anyone relying on the old silent clamp. Note that the failure surfaces at import time.
- [ ] 8.4 File a separate OpenSpec change proposal, "move ensure_runtime_setup out of module scope", covering `compose.py`'s module-scope call, the module-scope constructions in `transports/mcp.py`, the experiment runners that import `compose` at module scope, and the `VECTOR_STORE` path — so every fail-loud path gets true startup-time failure, not just the ones this incident fix touches.
- [ ] 8.5 Grep `docs/guides/` for any other place documenting the old warn-and-clamp behaviour or the old accepted-value sets and update it (doc-rot check per AGENTS.md Change Workflow).
- [ ] 8.6 File a separate OpenSpec change for `compose.py::_resolve_active_strategies`' silent `continue` on unregistered strategy names. This change sharpens the inconsistency (six provider settings now raise; `CHUNKING__STRATEGY_FALLBACK` and `METADATA__EXTRACTION_MODE` still have no validation at all), but fixing it requires separating inline-dispatched modes from typos — `METADATA__EXTRACTION_MODE=local` is valid and deliberately absent from the metadata registry, so a naive raise would break a supported config.

## 9. Validation

- [ ] 9.1 `openspec validate silent-failure-audit-and-guards --strict`
- [ ] 9.2 `uv run pytest -m "not slow" --cov=rag_mcp` — confirm `core/retrieval` and `config/` stay at or above the ≥95% coverage tier.
- [ ] 9.3 Manual check: start the server with a deliberately misconfigured `EMBED_PROVIDER` and confirm it fails fast naming that variable, not a downstream one.
