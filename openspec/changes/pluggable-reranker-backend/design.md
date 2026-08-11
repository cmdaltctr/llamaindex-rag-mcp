## Context

See `proposal.md` — Why. The constraints that shape the approach:

- The reranker is already registry-dispatched (`core/retrieval/registry.py:66`). Invariant 10 in `CLAUDE.md` says a new strategy is one file plus one `register()` line. The reranker is the only registry slot with a single entry, which is why the constraint reads as a wall rather than a choice.
- Two construction paths exist. `compose.build_reranker()` is the production path and injects the instance into `search()`. `pipeline.py:320` constructs one lazily when nothing is injected. Both hardcode the ONNX backend today.
- `_MODEL_CACHE` (`reranker.py:61`) is keyed by model ID alone and holds `(session, tokenizer, max_length)`.
- All three ADR-029 §3 deferred items landed in PR #27, **merged into `v3` at `67330ca`**: `_record_failure` (`reranker.py:82`) escalates to `logging.ERROR` after three consecutive same-signature failures, `last_failure_reason` is reset per call, and `pipeline.py:307-309` folds it into `rerank_reason`. This change inherits that work rather than repeating it, and adds only the backend name to diagnostics.
- `_effective_threshold` divides the similarity threshold by 30 when reranking. Calibrated in `experiments/1-reranker-threshold-calibration-2026-05-12/` against sigmoid-normalised scores: strong matches 0.79–1.0, weak-correct 0.015, noise below 0.003. PR #27 also gated the ÷30 on `rerank_succeeded` (`pipeline.py:320-323`), so a *failed* rerank no longer gets the scaled threshold. That guard reads the `reranked` flag, so it does not protect against a backend that succeeds while emitting scores on the wrong scale — see Risks.
- **This change targets `v3`, not `main`.** Breaking work goes to `v3`; `main` cuts a release on every push. PR #27 also targeted `v3`, and `v3` is 74 commits ahead of `main`. The dependency is already satisfied, so there is no blocker.
- Invariant 11: no file exceeds 500 lines. `reranker.py` is at 451.

## Goals / Non-Goals

**Goals:**
- Make backend choice a settings value that both construction paths honour.
- Sever the ONNX path from `transformers` permanently, so no upstream release can force an architecture decision.
- Guarantee score-range parity across backends, enforced by test rather than by review.
- Make the torch-free default install a CI-verified property, not a convention.
- Close the Apple-acceleration question with numbers. Experiment 16 killed CoreML. The torch backend opens the only untested route to the Apple GPU, which is MPS (Metal Performance Shaders). Experiment 17 measures it against the ONNX CPU baseline and records the answer in an ADR, so nobody asks again.

**Non-Goals:**
- Changing the default backend, default model, or any retrieval quality behaviour. A default install must produce byte-identical search results before and after.
- Re-running the ÷30 calibration. Sigmoid parity is required precisely so the existing calibration stays valid.
- Re-testing CoreML. Experiment 16 (2026-08-03) already measured it: fp16 + CoreML 5393 ms P50 against fp16 + CPU 5670 ms, so CoreML accelerated nothing. ORT partitions the graph and most operations fall back to CPU regardless. int8 + CPU won at 2348 ms. CoreML is settled and stays off.
- Changing the default execution provider. Experiment 17 measures; it does not switch anything on. Any default change is a follow-up change with its own ADR.
- PDF parser work. Widening the boundary makes Docling admissible for future evaluation; it does not evaluate it here.
- A generic "any inference engine" plugin API. Two backends, one contract, no speculative abstraction.

## Decisions

### 1. `tokenizers` replaces `transformers.AutoTokenizer`

`tokenizers` is already installed transitively, 9.2 MB against 56 MB, pure Rust, and structurally incapable of importing `torch`. The ONNX path uses exactly one `transformers` symbol.

The one behavioural gap: `tokenizers.Tokenizer` does not expose `model_max_length`. The existing code reads it off the tokenizer and guards against sentinel values (`reranker.py:311-317`). Replacement reads `config.json` from the same HuggingFace snapshot via `huggingface_hub` and takes `max_position_embeddings`, falling back to `TOKENIZER_MAX_LENGTH` when absent. The existing sentinel guard logic carries over unchanged.

*Alternatives:* pin `transformers<5` forever — defers the problem and ages out of tokeniser fixes. Vendor a tokeniser — absurd for this scope.

### 2. Cache key becomes `(backend, model_id)`

Two backends can be asked for the same model ID. Today's key would collide an `onnxruntime.InferenceSession` with a `sentence_transformers.CrossEncoder` under one entry, and whichever loaded second would hand the wrong object to the first. The tuple shape also differs between backends.

The cache moves to a shared module, `core/retrieval/_reranker_cache.py`, keyed by `(backend_name, model_id)`, with `reset_model_cache()` re-exported from both backend modules so the existing test teardown contract (gotcha 2 in `CLAUDE.md`) keeps working from either import site.

`_FAILURE_STATE` stays a single process-wide counter, unkeyed. That was deliberate — the docstring at `reranker.py:72-77` records the split-counter trap. Adding a backend axis would reintroduce it.

### 3. Sigmoid parity is enforced by contract test, not by convention

`sentence_transformers.CrossEncoder.predict()` returns raw logits unless the model config declares an activation. The torch backend therefore calls `predict(..., activation_fn=None)` and applies the module's own `_sigmoid` — the same function the ONNX path uses — rather than trusting the library's default.

This is the highest-risk part of the change and it fails silently if wrong, so it gets a test that compares both backends over shared fixtures rather than a code comment.

*Alternative:* let each backend define its own normalisation and rescale the threshold per backend. Rejected — it multiplies the calibrated constant by the number of backends and each copy drifts independently.

### 4. Backend name resolves once, at the same boundary as every other setting

`RETRIEVAL__RERANK_BACKEND` lands in `RetrievalBlock` and flows through `EffectiveSettings` like every other lever (invariant 9). `compose.build_reranker()` maps it to a registry name. `pipeline.py:320` reads it off the already-resolved `resolved_settings` rather than re-resolving.

Registry names become `reranker_onnx` and `reranker_torch`. The bare `reranker` name is retired rather than aliased — a stale alias resolving to the wrong backend is exactly the silent-divergence failure this change exists to prevent, and `test_registry_contract.py` already asserts every registered name resolves.

*Alternative:* keep `reranker` as an alias for the default. Rejected for the reason above.

### 5. Missing extra degrades, it does not crash

`RETRIEVAL__RERANK_BACKEND=torch` without the extra installed raises `ImportError` inside the registry's lazy resolution. `compose.build_reranker()` catches it, logs at ERROR naming `uv sync --extra torch`, and returns the ONNX backend.

An unknown backend name is different and fails hard at settings resolution, because that is a typo the operator can fix immediately. A missing extra is a deployment state that should not take the server down.

### 6. Experiment 17 measures MPS, and it is the only acceleration route left

Three routes to the Apple hardware exist. Two are closed.

| Route | Needs torch | Status |
|---|---|---|
| CoreML via ONNX Runtime | No | Closed. Experiment 16 measured no gain. Graph partitions to CPU anyway. |
| CPU via ONNX Runtime | No | Current default. int8, 2348 ms P50 on ModernBERT. |
| MPS via PyTorch | Yes | Never measured. Opened by this change. |

The common belief that CoreML failed because PyTorch was absent is wrong on the mechanism. `onnxruntime` reports `CoreMLExecutionProvider` as available in a venv with no torch installed and no torch in `sys.modules`. CoreML is an Apple C++ framework reached natively, not through Python. The ADR-029 error, `Error in dynamically resizing for sequence length (error: -7)`, is a CoreML shape error, not an import error.

The belief is right about the consequence. With no torch there was one route to the fast hardware, it failed, and there was no second route. This change supplies it.

Experiment 17 therefore compares three cells on the **default MiniLM model**, because Experiment 16's numbers are for ModernBERT and are not a valid baseline here: ONNX int8 on CPU, torch on CPU, torch on MPS. Latency, cold start, peak memory, and ranking agreement against the ONNX baseline.

The experiment does not change any default. If MPS wins, the follow-up change adds device selection to the torch backend and carries its own ADR.

### 7. `reranker.py` is at 451 of 500 lines

Extracting the cache into `_reranker_cache.py` removes roughly 60 lines, which absorbs the tokeniser-swap delta. `tests/test_file_size_ceiling.py` enforces this, so it is a build failure rather than a review note if the budget is missed.

## Risks / Trade-offs

**Score-range drift between backends** → The ÷30 threshold silently admits everything or nothing. This is the ADR-029 failure shape in a new location, and PR #27's `rerank_succeeded` guard does not catch it: a torch backend emitting raw logits still sets `reranked=True`, so the guard passes and the scaled threshold is applied to scores it was never calibrated for. Mitigated by decision 3's contract test comparing top-ranked document and admitted-result count across backends on shared fixtures.

**`config.json` missing `max_position_embeddings`** → Effective max length falls back to the configured default, which may exceed the model's real limit and produce an ONNX broadcast error at inference. Mitigated by keeping the existing sentinel guard and adding a scenario for the missing-value case. The failure is loud, not silent.

**Removing `transformers` from base deps breaks an unnoticed consumer** → `grep -rn "^from transformers\|^import transformers" src/` returns one file today, but a transitive consumer could exist. Mitigated by running the full suite in a fresh venv with no extras before merge, not just the fast subset.

**Two backends double the "which one actually ran" surface** → This is precisely what cost five weeks in ADR-029. Mitigated by decision 4 (one resolution point, no aliases) and by shipping the diagnostics work in the same change rather than deferring it again.

**Torch backend rots from disuse** → It is not on the default path, so nothing exercises it in the fast suite. Accepted with mitigation: the contract test runs it under the `slow` marker, and CI runs the slow suite on a schedule. If that proves insufficient, the honest response is to remove the backend rather than ship a broken option.

## Migration Plan

Additive for operators. No env var changes required, no re-ingestion, no index rebuild. An existing `.env` produces identical behaviour because the default is `onnx`.

Two things to call out in the release notes:

1. `transformers` leaves the base install. Anyone importing it from their own code alongside this package must add it themselves. This is why the change is marked BREAKING at the dependency level despite no API change.
2. `uv sync --extra torch` is opt-in and adds roughly 200 MB on macOS ARM, more on Linux where `pip` resolves the CUDA stack by default.

Rollback: revert the commit. No persisted state changes, so nothing to undo in ChromaDB or on disk beyond the venv.

Sequencing matters within the change. The tokeniser swap and the base-dependency removal land together — doing the removal first leaves the ONNX path importing a package that is no longer declared.

## Open Questions

- Whether `sentence-transformers>=3.0` is the right floor, or whether v4/v5 should be the minimum. Resolvable at implementation time against whatever is current; it does not change the specs, the approach, or the task breakdown.
- Whether the slow-suite CI schedule needs a dedicated job for the torch extra or can extend the existing one. A CI configuration detail, deferrable to the PR.
