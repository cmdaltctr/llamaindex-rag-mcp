> **Target branch is `v3`, not `main`.** Breaking work goes to `v3`; `main` cuts a
> release on every push. PR #27 already merged into `v3` at `67330ca`, so the
> `pipeline.py` work this change builds on is already present. No blocker.

## 1. Settings and registry wiring

- [x] 1.1 Add `rerank_backend: str = "onnx"` to `RetrievalSettings` in `src/rag_mcp/core/retrieval/settings.py`, then add a `_validate_provider_value(self.retrieval, "rerank_backend", ("onnx", "torch"), "RETRIEVAL__RERANK_BACKEND")` call to `_validate_provider_selections` in `src/rag_mcp/config/__init__.py` — this matches the existing `hybrid_sparse_backend` pattern (plain `str` + explicit validator, not `Literal`), so whitespace is stripped, empty resets to default, and the error message names the accepted values
- [x] 1.2 Add `rerank_backend: str = "onnx"` to `RetrievalBlock` in `src/rag_mcp/core/settings.py` — `RetrievalBlock` uses `ConfigDict(frozen=True)` with no `extra` override, so Pydantic defaults to `extra="ignore"` and any field not declared here is silently dropped during `compose.settings_to_effective`'s `RetrievalBlock(**settings.retrieval.model_dump())` copy
- [x] 1.3 Add a test asserting `compose.settings_to_effective(defaults).retrieval.rerank_backend == "onnx"` to catch the silent-drop class of regression
- [x] 1.4 Rename `register("reranker", ...)` to `register("reranker_onnx", ...)` in `src/rag_mcp/core/retrieval/registry.py`; do NOT keep `reranker` as an alias (design decision 4)
- [x] 1.5 Verify `RETRIEVAL__RERANK_BACKEND=tensorflow` fails at settings resolution with `pytest.raises(ValueError, match="RETRIEVAL__RERANK_BACKEND.*Accepted values: onnx, torch")`

## 2. Extract the model cache

- [x] 2.1 Create `src/rag_mcp/core/retrieval/_reranker_cache.py` holding `_MODEL_CACHE`, `_CACHE_LOCK`, `_FAILURE_STATE`, `_FAILURE_THRESHOLD`, `_record_failure`, `_reset_failure_state`, and `reset_model_cache`
- [x] 2.2 Change the cache key from `model_id` to `(backend_name, model_id)`; keep `_FAILURE_STATE` as a single unkeyed process-wide counter and carry over the split-counter-trap comment from `reranker.py:72-77`
- [x] 2.3 Re-export `reset_model_cache` from `core/retrieval/reranker.py` so the existing test teardown import path keeps working (gotcha 2)
- [x] 2.4 Run `uv run pytest tests/test_reranker.py -v` and confirm green before touching the tokeniser

## 3. ONNX backend: swap the tokeniser

- [x] 3.1 Replace `from transformers import AutoTokenizer` with `from tokenizers import Tokenizer` in `core/retrieval/reranker.py`; load via `Tokenizer.from_pretrained(model_id)`
- [x] 3.2 Replace the `model_max_length` read (`reranker.py:311-317`) with a `config.json` fetch via `huggingface_hub`, taking `max_position_embeddings`; keep the existing sentinel guard and the `TOKENIZER_MAX_LENGTH` fallback
- [x] 3.3 Port the batch encoding call (`reranker.py:418`) to the `tokenizers` API: `enable_truncation(max_length)`, `enable_padding()`, then `encode_batch(pairs)`. Three things the `tokenizers` API does differently from `AutoTokenizer`: (a) property rename — `Encoding.ids` → `input_ids`, `Encoding.type_ids` → `token_type_ids`, `Encoding.attention_mask` → `attention_mask`; (b) dtype cast — `tokenizers` returns Python lists (u32 underneath), ONNX Runtime expects `int64`, so wrap each in `np.asarray(..., dtype=np.int64)` explicitly; (c) model-family variation — BERT-family models produce `token_type_ids`, some other families do not. Omit `token_type_ids` from the feed dict when the ONNX graph's `input_names` does not declare it, or ORT raises a cryptic input-name error. Add a pair-truncation and padding test against a recorded fixture
- [x] 3.4 Update the module docstring to state `tokenizers`, not `transformers`
- [x] 3.5 Run `uv run pytest tests/test_reranker.py -m "not slow" -v` and confirm identical scores against a recorded fixture from before the swap

## 4. Torch backend

- [x] 4.1 Create `src/rag_mcp/core/retrieval/reranker_torch.py` with `SentenceTransformerReranker`, matching `CrossEncoderReranker`'s constructor signature (`model_id`, `tokenizer_max_length`) and public surface (`rerank`, `last_failure_reason`)
- [x] 4.2 Import `sentence_transformers` lazily inside the load method, never at module top level, so registry import stays cheap and the missing-extra case is catchable
- [x] 4.3 Call `CrossEncoder.predict(..., activation_fn=torch.nn.Identity())` to suppress the library's default sigmoid, then apply the shared `_sigmoid` once — `activation_fn=None` does NOT disable activation; for `num_labels=1` the library defaults to `nn.Sigmoid()`, which would double-apply sigmoid and compress scores to roughly `[0.5, 0.73]` (design decision 3)
- [x] 4.4 Reuse `_reranker_cache` for the model cache and the failure-escalation counter; set `_reranked` and `last_failure_reason` on the same contract as the ONNX backend
- [x] 4.5 Match the graceful-degradation path: model load failure returns un-reranked results truncated to `top_k`, never raises
- [x] 4.6 Add `register("reranker_torch", "rag_mcp.core.retrieval.reranker_torch:SentenceTransformerReranker")` to the retrieval registry

## 5. Route backend selection

- [x] 5.1 Extract a shared backend-resolution helper in `core/retrieval/` (not `compose.py` — `core/` must not import `compose`) that maps `settings.retrieval.rerank_backend` to a registry name, resolves it, and on `ImportError` logs at ERROR naming `uv sync --extra torch` and falls back to the ONNX backend. Both `compose.build_reranker()` and the lazy path in `pipeline.py` call this helper — two construction paths must not have two different fallback behaviours (design decision 5)
- [x] 5.2 In `core/retrieval/pipeline.py:320`, replace the hardcoded `_retrieval_get("reranker")` literal with a call to the shared resolution helper, reading the backend name off `resolved_settings.retrieval.rerank_backend`
- [x] 5.3 Add a test asserting the lazy path and the injected path select the same backend for the same settings
- [x] 5.4 Add a test for the missing-extra + ONNX-also-fails combined case: `RETRIEVAL__RERANK_BACKEND=torch` with no extra installed AND the ONNX backend failing to load — the search SHALL return un-reranked results truncated to `top_k`, set `last_failure_reason`, and never raise

## 6. Dependencies

- [x] 6.1 Remove `transformers>=4.40.0` from base `dependencies` in `pyproject.toml` and add `tokenizers>=0.20` — land this in the same commit as task 3
- [x] 6.2 Add the optional extra `torch = ["sentence-transformers>=5.0"]` — v3.x uses `activation_fct`, the `activation_fn` kwarg did not exist until v4.x, and v5.4+ changed `activation_fn` persistence on `predict()`; pin `>=5.0` so the Identity-override contract is stable
- [x] 6.3 Run `grep -rn "transformers" src/` and confirm the only remaining hits are inside `reranker_torch.py` or comments
- [x] 6.4 Run `uv sync` in a fresh venv with no extras and confirm `uv pip list | grep -iE "^torch|^transformers"` returns nothing

## 7. Diagnostics

> PR #27 already landed failure escalation, per-call reset, and the
> `last_failure_reason` → `rerank_reason` fold at `pipeline.py:327-329`. Only the
> backend-name field is new here.

- [x] 7.1 Confirm on the rebased branch that `pipeline.py:327-329` still folds `last_failure_reason` into `rerank_reason`, and that the torch backend populates that attribute on the same contract
- [x] 7.2 Attach the active backend name to diagnostics alongside the existing `rerank_reason`
- [x] 7.3 Confirm the `rerank_backend` diagnostic is only added when `include_diagnostics=True` (the strip at `pipeline.py:355-356` runs only when `False`, so a field added the same way as `rerank_reason` needs no strip-list entry — verify this rather than assume)
- [x] 7.4 Confirm the `rerank_succeeded` guard at `pipeline.py:340-343` behaves identically under the torch backend — a failed torch load must leave raw cosine scores un-scaled

## 8. Tests

- [x] 8.1 Add `tests/test_reranker_backend_contract.py`: parametrise over every registered reranker backend and assert scores fall in `(0, 1)`, results are sorted descending, `_reranked` is set, and `top_k` truncation holds
- [x] 8.2 Add a cross-backend agreement test over shared fixtures: same model ID, same query, same candidates — assert the top-ranked document matches **and** the score values agree within a tolerance (e.g. `abs(onnx_score - torch_score) < 0.01`). Checking only ranking and the `(0, 1)` range would miss a double-sigmoid bug, which preserves monotonicity and stays in range but compresses the score scale
- [x] 8.3 Add `tests/test_no_torch_at_runtime.py`: import `rag_mcp`, run a search with `rerank=True` on the default backend, assert `"torch" not in sys.modules`
- [x] 8.4 Add a dependency-audit test asserting `sentence-transformers`, `torch`, `optimum`, and `transformers` are absent from `[project.dependencies]` in `pyproject.toml`
- [x] 8.5 Mark every torch-backend test `@pytest.mark.slow` and confirm `uv run pytest -m "not slow"` neither imports nor requires torch
- [x] 8.6 Verify each new test fails when its target is broken — delete the sigmoid call in the torch backend and confirm 8.2 goes red (score-value assertion, not just ranking) before restoring it
  - **Verified 2026-08-11.** Replaced `_sigmoid(float(v))` with `float(v)` in `reranker_torch.py:223`; `test_cross_backend_top_ranked_matches` failed with `delta=9.513893` (ONNX=0.999971, torch=10.513865) on the score-value assertion while the ranking assertion still passed — confirming a ranking-only test would miss the bug. Restored; test green.
- [x] 8.7 Add `tests/test_registry_contract.py` parametrised test resolving every name in `retrieval_registry.available()` so a broken `reranker_torch` registration is caught — the existing test only resolves `available()[0]` (`"bm25"`), not `"reranker_onnx"` or `"reranker_torch"`
- [x] 8.8 Add a test asserting the retired bare `"reranker"` name raises `KeyError` listing `"reranker_onnx"` and `"reranker_torch"`
- [x] 8.9 Update `tests/test_hybrid_retrieval.py:874` — it monkeypatches `retrieval_registry._cache["reranker"]`, which will be `KeyError` after the rename; change it to the settings-selected name (`"reranker_onnx"` for the default)
- [x] 8.10 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm `core/retrieval` stays at or above the 95% tier floor

## 9. Experiment 17 — Apple acceleration, settled

> **Moved to `openspec/changes/apple-acceleration-for-reranker/`** on
> 2026-08-11. Experiment 17 is research that produces an ADR and
> potentially a follow-up code change; it is separable from the
> pluggable-backend code change and task 9.11 already anticipates a
> follow-up change if MPS wins. Holding the PR open for a multi-day
> benchmark would block dependent v3 work. See the new change for the
> full task list (9.1–9.11 carried over verbatim).

- [~] 9.1–9.11 → moved to `openspec/changes/apple-acceleration-for-reranker/tasks.md`

## 10. Documentation

- [x] 10.1 Amend the `🚫 Never` row in `CLAUDE.md` to the scoped wording: no PyTorch in the base install or on the default retrieval path; PyTorch behind an optional extra is ⚠️ Ask
- [x] 10.2 Add `RETRIEVAL__RERANK_BACKEND` to `.env.example` and `docs/guides/configuration.md`
- [x] 10.3 Update `docs/guides/reranker.md` with the backend table, the `uv sync --extra torch` instruction, and the sigmoid-parity note
- [x] 10.4 Write `docs/adr/038-pluggable-reranker-backend.md` scoping (not reversing) ADR-005, recording the `transformers` v5 trap as the trigger, and cross-referencing ADR-029 for why observability shipped alongside. Measure the actual install-size delta in a fresh venv (`uv pip list --format=freeze` before and after, then `diff`) and record the real number — the 47 MB estimate compares isolated wheel sizes and likely overstates the saving because `tokenizers` and `huggingface-hub` are already pulled transitively by `chromadb`
- [x] 10.5 Grep `docs/guides/` for now-stale claims that the project has no PyTorch path at all

## 11. Validation and PR

- [x] 11.1 Run `openspec validate --all --strict`
- [x] 11.2 Run `uv run lint-imports` — the new `reranker_torch.py` under `core/retrieval/` is subject to the `core-business-avoids-providers-transports` contract
- [x] 11.3 Run the full suite including slow tests in a venv with the `torch` extra installed: `uv sync --extra torch && uv run pytest -m "slow" -k "torch or backend_contract"`
  - **Covered by CI.** The "Torch backend tests" job in `.github/workflows/ci.yml` installs `uv sync --extra torch` and runs the torch-backend and cross-backend contract tests without `|| echo` suppression (task 11.5). The job passed on the latest push (run 31529900218). Also verified locally: `uv sync --extra torch && uv run pytest -m "slow" -k "torch or backend_contract"` — `test_cross_backend_top_ranked_matches` passed in 42.6s.
- [x] 11.4 Run the full suite in a fresh venv with no extras and confirm it passes without torch: `uv sync && uv run pytest -m "not slow"`
- [x] 11.5 Add a dedicated CI job in `.github/workflows/ci.yml` that installs with `uv sync --extra torch` and runs the torch-backend and cross-backend contract tests without `|| echo` suppression — the existing slow job has no schedule and swallows failures, so the torch backend is never exercised otherwise
- [x] 11.6 Confirm the default-install CI job stays torch-free: `uv sync --frozen` with no extras, then `uv pip list | grep -iE "^torch|^transformers"` returns nothing
- [x] 11.7 Commit with Conventional Commits (`feat!:` — base dependency removal is breaking) and open the PR against **`v3`**, not `main`
  - **Done.** PR #37 is open against `v3`, mergeable CLEAN, all CI green.
