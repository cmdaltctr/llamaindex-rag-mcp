> **Target branch is `v3`, not `main`.** Breaking work goes to `v3`; `main` cuts a
> release on every push. PR #27 already merged into `v3` at `67330ca`, so the
> `pipeline.py` work this change builds on is already present. No blocker.

## 1. Settings and registry wiring

- [ ] 1.1 Add `rerank_backend: Literal["onnx", "torch"] = "onnx"` to `RetrievalSettings` in `src/rag_mcp/core/retrieval/settings.py`, with a docstring naming the two values
- [ ] 1.2 Confirm `RetrievalBlock` in `src/rag_mcp/core/settings.py` picks the field up via `model_dump()` in `compose.settings_to_effective` — no restatement needed if the 1:1 copy holds
- [ ] 1.3 Rename `register("reranker", ...)` to `register("reranker_onnx", ...)` in `src/rag_mcp/core/retrieval/registry.py`; do NOT keep `reranker` as an alias (design decision 4)
- [ ] 1.4 Verify `RETRIEVAL__RERANK_BACKEND=tensorflow` fails at settings resolution with a message naming the accepted values

## 2. Extract the model cache

- [ ] 2.1 Create `src/rag_mcp/core/retrieval/_reranker_cache.py` holding `_MODEL_CACHE`, `_CACHE_LOCK`, `_FAILURE_STATE`, `_FAILURE_THRESHOLD`, `_record_failure`, `_reset_failure_state`, and `reset_model_cache`
- [ ] 2.2 Change the cache key from `model_id` to `(backend_name, model_id)`; keep `_FAILURE_STATE` as a single unkeyed process-wide counter and carry over the split-counter-trap comment from `reranker.py:72-77`
- [ ] 2.3 Re-export `reset_model_cache` from `core/retrieval/reranker.py` so the existing test teardown import path keeps working (gotcha 2)
- [ ] 2.4 Run `uv run pytest tests/test_reranker.py -v` and confirm green before touching the tokeniser

## 3. ONNX backend: swap the tokeniser

- [ ] 3.1 Replace `from transformers import AutoTokenizer` with `from tokenizers import Tokenizer` in `core/retrieval/reranker.py`; load via `Tokenizer.from_pretrained(model_id)`
- [ ] 3.2 Replace the `model_max_length` read (`reranker.py:311-317`) with a `config.json` fetch via `huggingface_hub`, taking `max_position_embeddings`; keep the existing sentinel guard and the `TOKENIZER_MAX_LENGTH` fallback
- [ ] 3.3 Port the batch encoding call (`reranker.py:418`) to the `tokenizers` API: `enable_truncation(max_length)`, `enable_padding()`, then `encode_batch(pairs)`; build the `input_ids` / `attention_mask` / `token_type_ids` numpy arrays the ONNX session expects
- [ ] 3.4 Update the module docstring to state `tokenizers`, not `transformers`
- [ ] 3.5 Run `uv run pytest tests/test_reranker.py -m "not slow" -v` and confirm identical scores against a recorded fixture from before the swap

## 4. Torch backend

- [ ] 4.1 Create `src/rag_mcp/core/retrieval/reranker_torch.py` with `SentenceTransformerReranker`, matching `CrossEncoderReranker`'s constructor signature (`model_id`, `tokenizer_max_length`) and public surface (`rerank`, `last_failure_reason`)
- [ ] 4.2 Import `sentence_transformers` lazily inside the load method, never at module top level, so registry import stays cheap and the missing-extra case is catchable
- [ ] 4.3 Call `CrossEncoder.predict(..., activation_fn=None)` and apply the shared `_sigmoid` explicitly — do not rely on the library's default activation (design decision 3)
- [ ] 4.4 Reuse `_reranker_cache` for the model cache and the failure-escalation counter; set `_reranked` and `last_failure_reason` on the same contract as the ONNX backend
- [ ] 4.5 Match the graceful-degradation path: model load failure returns un-reranked results truncated to `top_k`, never raises
- [ ] 4.6 Add `register("reranker_torch", "rag_mcp.core.retrieval.reranker_torch:SentenceTransformerReranker")` to the retrieval registry

## 5. Route backend selection

- [ ] 5.1 In `compose.build_reranker()`, resolve the registry name from `settings.retrieval.rerank_backend` instead of importing `CrossEncoderReranker` directly
- [ ] 5.2 Wrap the registry resolution in `try/except ImportError`, log at ERROR naming `uv sync --extra torch`, and fall back to the ONNX backend (design decision 5)
- [ ] 5.3 In `core/retrieval/pipeline.py:320`, read the backend name off the already-resolved `resolved_settings` rather than the hardcoded `_retrieval_get("reranker")` literal
- [ ] 5.4 Add a test asserting the lazy path and the injected path select the same backend for the same settings

## 6. Dependencies

- [ ] 6.1 Remove `transformers>=4.40.0` from base `dependencies` in `pyproject.toml` and add `tokenizers>=0.20` — land this in the same commit as task 3
- [ ] 6.2 Add the optional extra `torch = ["sentence-transformers>=3.0"]`
- [ ] 6.3 Run `grep -rn "transformers" src/` and confirm the only remaining hits are inside `reranker_torch.py` or comments
- [ ] 6.4 Run `uv sync` in a fresh venv with no extras and confirm `uv pip list | grep -iE "^torch|^transformers"` returns nothing

## 7. Diagnostics

> PR #27 already landed failure escalation, per-call reset, and the
> `last_failure_reason` → `rerank_reason` fold at `pipeline.py:307-309`. Only the
> backend-name field is new here.

- [ ] 7.1 Confirm on the rebased branch that `pipeline.py:307-309` still folds `last_failure_reason` into `rerank_reason`, and that the torch backend populates that attribute on the same contract
- [ ] 7.2 Attach the active backend name to diagnostics alongside the existing `rerank_reason`
- [ ] 7.3 Confirm `_strip_internal_result_fields` removes the new backend field when `include_diagnostics=False`, so the public result shape is unchanged
- [ ] 7.4 Confirm the `rerank_succeeded` guard at `pipeline.py:320-323` behaves identically under the torch backend — a failed torch load must leave raw cosine scores un-scaled

## 8. Tests

- [ ] 8.1 Add `tests/test_reranker_backend_contract.py`: parametrise over every registered reranker backend and assert scores fall in `(0, 1)`, results are sorted descending, `_reranked` is set, and `top_k` truncation holds
- [ ] 8.2 Add a cross-backend agreement test over shared fixtures: same model ID, same query, same candidates — assert the top-ranked document matches and the admitted-result count under a fixed threshold differs by at most one
- [ ] 8.3 Add `tests/test_no_torch_at_runtime.py`: import `rag_mcp`, run a search with `rerank=True` on the default backend, assert `"torch" not in sys.modules`
- [ ] 8.4 Add a dependency-audit test asserting `sentence-transformers`, `torch`, `optimum`, and `transformers` are absent from `[project.dependencies]` in `pyproject.toml`
- [ ] 8.5 Mark every torch-backend test `@pytest.mark.slow` and confirm `uv run pytest -m "not slow"` neither imports nor requires torch
- [ ] 8.6 Verify each new test fails when its target is broken — delete the sigmoid call in the torch backend and confirm 8.2 goes red before restoring it
- [ ] 8.7 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm `core/retrieval` stays at or above the 95% tier floor

## 9. Experiment 17 — Apple acceleration, settled

> Run this AFTER task group 4, so a working torch backend exists to measure.
> Load the `s-experiment` skill first. Do NOT run this before the backend works —
> a benchmark of broken code is worse than no benchmark.
>
> Scope note: CoreML is NOT re-tested. Experiment 16 (2026-08-03) already measured
> it and found no acceleration. MPS (Metal Performance Shaders, the Apple GPU path
> in PyTorch) is the only untested route, and this change is what makes it reachable.

- [ ] 9.1 Create `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/` from `experiments/EXP_PROTOCOL_TEMPLATE.md`
- [ ] 9.2 Write `protocol.md` with three cells, all on the **default MiniLM model** — Experiment 16's numbers are for ModernBERT and are not a valid baseline here: (17A) ONNX int8 on CPU, (17B) torch on CPU, (17C) torch on MPS
- [ ] 9.3 State the pass gates before running: H1 — torch on MPS loads without error; H2 — 17C P50 latency beats 17A P50 by at least 20%; H3 — 17C cold start no worse than 3× 17A; H4 — 17C top-ranked document matches 17A on every workload query
- [ ] 9.4 Reuse the Experiment 16 runner shape: each cell in a **separate process**. Experiment 16 finding 4 recorded that loading int8 first corrupts ORT global optimiser state and poisons later cells in the same process
- [ ] 9.5 Write `run_eval.py` with checkpoint and `--resume`, `print(..., flush=True)`, and atomic writes to `output/` (`.tmp` then rename), per the experiment discipline in `CLAUDE.md`
- [ ] 9.6 Record latency P50/P95/mean, cold start, and peak RSS per cell, matching Experiment 16's results table columns so the two are comparable
- [ ] 9.7 Run 5 warm iterations × 5 queries × 20 docs, matching Experiment 16's shape
- [ ] 9.8 Write `results.md` with the cell table, the pass-gate outcomes, and a plain recommendation
- [ ] 9.9 Write `docs/adr/039-apple-acceleration-for-the-reranker.md` recording all three routes and their verdicts: CoreML closed by Exp 16, CPU as current default, MPS decided by Exp 17. State plainly that CoreML did not fail because PyTorch was absent, and give the evidence
- [ ] 9.10 Add the Exp 17 row to `experiments/EXP_README.md`
- [ ] 9.11 If MPS wins: do NOT change the default in this change. Open a follow-up change for torch device selection, and note it in the ADR's consequences

## 10. Documentation

- [ ] 10.1 Amend the `🚫 Never` row in `CLAUDE.md` to the scoped wording: no PyTorch in the base install or on the default retrieval path; PyTorch behind an optional extra is ⚠️ Ask
- [ ] 10.2 Add `RETRIEVAL__RERANK_BACKEND` to `.env.example` and `docs/guides/configuration.md`
- [ ] 10.3 Update `docs/guides/reranker.md` with the backend table, the `uv sync --extra torch` instruction, and the sigmoid-parity note
- [ ] 10.4 Write `docs/adr/038-pluggable-reranker-backend.md` scoping (not reversing) ADR-005, recording the `transformers` v5 trap as the trigger, and cross-referencing ADR-029 for why observability shipped alongside
- [ ] 10.5 Grep `docs/guides/` for now-stale claims that the project has no PyTorch path at all

## 11. Validation and PR

- [ ] 11.1 Run `openspec validate --all --strict`
- [ ] 11.2 Run the full suite including slow tests in a venv with the `torch` extra installed
- [ ] 11.3 Run the full suite in a fresh venv with no extras and confirm it passes without torch
- [ ] 11.4 Commit with Conventional Commits (`feat!:` — base dependency removal is breaking) and open the PR against **`v3`**, not `main`
