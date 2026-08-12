# ADR-040: huggingface-hub 1.0 + transformers 5.0 Upgrade

**Date:** 2026-08-12
**Status:** Accepted
**Scopes:** ADR-038 (pluggable reranker backend — the `torch` extra's `transformers` pin is lifted; the `activation_fn` contract on `CrossEncoder.predict()` is preserved in sentence-transformers 5.7.0)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The v3 minor-upgrade window (ADR-037 / commit 715fa7b) capped
`huggingface-hub<1` and `transformers<5` because both 1.0/5.0 releases
rewrote public APIs. ADR-039 lifted the mcp cap; this ADR lifts the
remaining two.

The two caps are **coupled**: every `transformers>=4.40.0,<5` version
declares `huggingface-hub<1.0` as a dependency. Lifting
`huggingface-hub>=1.0.0` in the base install makes the lock unsatisfiable
unless the `transformers<5` cap in the `torch` extra is lifted
simultaneously. They cannot be done independently.

### huggingface-hub 1.0 breaking changes

The official migration guide lives at
<https://huggingface.co/docs/huggingface_hub/main/en/concepts/migration>.
The headline changes:

1. **`requests` → `httpx`** — all HTTP now goes through `httpx` instead
   of `requests`/`aiohttp`. Error classes changed: `HfHubHttpError` is
   now a subclass of `httpx.HTTPError` (was `requests.HTTPError`).
   `SSLError` is now a generic `httpx.ConnectError`. `LocalEntryNotFoundError`
   no longer inherits from `HTTPError`; a new `EntryNotFoundError` unifies
   local/remote not-found.
2. **Removed params from `hf_hub_download`/`snapshot_download`:**
   `resume_download`, `force_filename`, `local_dir_use_symlinks`.
3. **`Repository` class removed** (git CLI wrapper) — use `HfApi` instead.
4. **`HfFolder` class removed** — use `login()`/`logout()`/`get_token()`.
5. **`InferenceApi` class removed** — use `InferenceClient`.
6. **`use_auth_token` param removed** from all methods — use `token`.
7. **`hf_transfer` support removed** — use `HF_XET_HIGH_PERFORMANCE`.
8. **CLI: `huggingface-cli` removed**, `hf` replaces it; cache commands
   redesigned (`hf cache ls/rm/prune`).

### What this project actually uses

Only `hf_hub_download(repo_id=..., filename=...)` — in two files:
- `core/retrieval/reranker.py` (ONNX backend: downloads `.onnx` model)
- `core/retrieval/_model_config.py` (reads `config.json` and
  `tokenizer_config.json` for max_position_embeddings and pad_token)

No `requests` imports, no `HfHubHttpError`/`LocalEntryNotFoundError`
catches, no `use_auth_token`, no `resume_download`/`force_filename`/
`local_dir_use_symlinks`, no `Repository`/`HfFolder`/`InferenceApi`.
Both call sites catch bare `Exception` and log+fallback, so the
error-class rename is insulated.

### transformers 5.0 breaking changes

transformers 5.0 reworks the model loading API. This project does NOT
import `transformers` directly in any source file — it is a transitive
dependency of `sentence-transformers` in the opt-in `torch` extra. The
torch reranker (`reranker_torch.py`) uses
`sentence_transformers.CrossEncoder` only.

ADR-038 flagged that "v5.4+ changed `activation_fn` persistence on
`predict()`." Verified against sentence-transformers 5.7.0:
`CrossEncoder.predict()` still accepts `activation_fn=` as a keyword
parameter, and `torch.nn.Identity()` still works to suppress the
default sigmoid. The `reranker_torch.py` code is compatible.

## Decision

Lift both caps and upgrade to the v1.0/v5.0 API surface.

### Source changes

**None.** The `hf_hub_download(repo_id=..., filename=...)` signature is
unchanged. No removed params or error classes are used. No `transformers`
direct imports exist.

### `pyproject.toml` changes

- Base: `"huggingface-hub>=0.20.0,<1"` → `"huggingface-hub>=1.0.0"`
- `torch` extra: `"transformers>=4.40.0,<5"` → `"transformers>=5.0.0"`
- Comment block updated to reflect both caps lifted and the coupling.

### Test changes

**None.** Tests patch `huggingface_hub.hf_hub_download` by name —
unchanged in v1.0. The `test_torch_missing_*` tests assume the torch
extra is absent (normal fast-suite environment); they still pass when
it is absent and correctly fail when it is installed (expected — the
fallback path doesn't trigger when the extra is present).

## Alternatives considered

- **Lift only huggingface-hub, keep transformers<5.** Rejected — the
  lock is unsatisfiable: all `transformers<5` versions require
  `huggingface-hub<1.0`.
- **Keep both caps.** Rejected — same reasoning as ADR-039: the caps
  exist for the minor-upgrade window only; aging out of fixes is the
  trap the major-upgrade cycle exists to escape.

## Consequences

- **Positive:** `httpx`-based HTTP backend (thread-safe, HTTP/2,
  connection reuse); on the latest `tokenizers`/`transformers` fix
  cycle.
- **Neutral:** `requests` is no longer pulled transitively by
  huggingface-hub; this project doesn't use `requests` directly, so no
  impact. `aiohttp` also dropped (not used).
- **Watch:** if future code needs to catch huggingface HTTP errors
  specifically, use `huggingface_hub.HfHubHttpError` (not
  `httpx.HTTPError` or `requests.HTTPError`) for cross-version
  compatibility.
- **Watch:** `hf_transfer` is gone; if high-performance downloads were
  ever needed, use `HF_XET_HIGH_PERFORMANCE` instead of
  `HF_HUB_ENABLE_HF_TRANSFER`.

## Verification

- `uv lock --upgrade`: `huggingface-hub 0.36.2 → 1.27.0`,
  `transformers 4.57.6 → 5.15.0` (torch extra only).
- `uv sync` (base): clean — huggingface-hub 1.27.0 installed, no
  transformers in base.
- `uv sync --extra torch`: clean — transformers 5.15.0,
  sentence-transformers 5.7.0, torch 2.13.0.
- `CrossEncoder.predict(activation_fn=torch.nn.Identity())` verified
  working on sentence-transformers 5.7.0.
- `uv run pytest -m "not slow"`: **1201 passed, 3 skipped** (base
  install, no torch extra — the normal CI path).
