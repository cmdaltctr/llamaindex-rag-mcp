## Why

The major dependency upgrade cycle lifted every upper cap in `pyproject.toml`
(mcp 2.0, huggingface-hub 1.0, transformers 5.0, onnxruntime 1.28) and the
lockfile now resolves at ceiling: `uv lock --upgrade` reports no changes. The
lower bounds were never touched. Sixteen of them now sit one or more majors
below the versions the test suite actually exercises, and CI installs with
`uv sync --frozen`, so no job has ever run the declared floors.

Two of those floors are not merely stale, they are wrong.

**chromadb.** `chromadb>=0.5.0` admits the entire 0.6.0 to 0.9.x range, where
`list_collections()` returns collection names as strings instead of
`Collection` objects. Chroma's migration log records the break at v0.6.0
(2024-12-30) and the revert at v1.0.0 (2025-03-01): "`list_collections` now
reverts back to returning `Collection` objects"
([chroma migration log](https://docs.trychroma.com/docs/overview/migration)).
`ChromaVectorStoreAdapter.list_collections` at
`src/rag_mcp/core/vectordb/chroma.py:119` does `[c.name for c in
client.list_collections()]` and raises `AttributeError: 'str' object has no
attribute 'name'` across that whole range. The llama-index chroma adapter does
not shield us: it dropped its own `chromadb<0.6.0` pin at version 0.3.0 and
never re-added an upper bound.

**tree-sitter-language-pack.** `tree-sitter-language-pack>=0.1.0` sits nine
majors below the locked 1.14.3 and admits 1.8.0 through 1.12.2, where
`get_parser()` returned a vendored parser class rather than
`tree_sitter.Parser`. Upstream's 1.12.3 entry records both failure modes: on
Python 3.14 the vendored parser "produced unusable trees ... while nothing
failed at construction, so the breakage was silent", and on Python below 3.14
an invalid `_rust.Parser` return annotation "broke import"
([CHANGELOG 1.12.3](https://github.com/xberg-io/tree-sitter-language-pack/blob/main/CHANGELOG.md),
[issue #157](https://github.com/xberg-io/tree-sitter-language-pack/issues/157)).
`ast_extract.py` calls `get_parser(lang)` then `parser.parse(content_bytes)`
inside a broad `try/except`, so the silent variant degrades every AST
extraction to a logged warning per file rather than a visible failure. The
project declares `requires-python = ">=3.11"`, so both variants are inside the
supported matrix.

Running `uv lock --resolution lowest-direct` shows what the declared contract
resolves to today: chromadb 0.5.17, tree-sitter-language-pack 0.1.0,
tree-sitter 0.22.0, networkx 3.0, onnxruntime 1.17.0, httpx 0.27.0,
liteparse 2.0.0, watchdog 4.0.0, llama-index-llms-ollama 0.7.2. That stack has
never been installed, never been tested, and is not what the project supports.

## What Changes

- Raise every stale lower bound in `pyproject.toml` to the lowest version
  proven safe against the project's actual API usage, with an upstream
  changelog or release-note citation per package. Where no intermediate
  version is defensible, the floor moves to the locked version.
- **BREAKING** `chromadb` moves from `>=0.5.0` to `>=1.0.0`. This is the fix
  for the `list_collections` regression, not a cosmetic bump.
- **BREAKING** `tree-sitter-language-pack` moves from `>=0.1.0` to `>=1.12.3`,
  and `tree-sitter` from `>=0.21.0` to `>=0.23.0` (the minimum the language
  pack itself declares).
- **BREAKING** the `llama-index` family floors move up together
  (`llama-index`, `llama-index-vector-stores-chroma`,
  `llama-index-readers-file`, `llama-index-embeddings-ollama`,
  `llama-index-llms-ollama`) so the adapter and core stay a coherent set
  under chromadb 1.x.
- Raise `watchdog` to `>=5.0.0`, `networkx` to `>=3.2`, and `onnxruntime` to
  `>=1.20.0`. Leave `httpx`, `tokenizers`, `typer`, `pyyaml`,
  `pydantic-settings`, `python-dotenv`, and `docx2txt` where they are: each is
  already at or near its locked version, or has no breaking change in the gap.
- Add a CI job that resolves and installs with `--resolution lowest-direct`
  and runs the fast test suite. This converts the floors from a comment into
  a tested contract. Without it they rot again on the next upgrade cycle.
- Add an automated check that no declared floor sits below the version in
  `uv.lock` by more than one minor, so drift is caught at review time rather
  than at the next audit.
- Record ADR-042 with the per-package evidence table and the floor policy.
- Leave the five upstream-blocked transitives alone (openai 3.0, pandas 3.0,
  marshmallow 4.x, tokenizers 0.23.1, striprtf). Each is held by
  llama-index, chromadb, or transformers, and none is ours to move. Document
  them as watch items in the ADR.
- No fix for the native sparse capability probe, which this change's research
  exposed. `detect_native_sparse_capability` at `core/vectordb/chroma.py:390`
  tests `hasattr(chromadb.PersistentClient, "query_sparse")`, a name ChromaDB
  never shipped. Verified against the installed chromadb 1.5.9: sparse search
  exists, exposed as `Search()` / `Knn(key=...)` / `Collection.search()`, so
  the probe's forward-compatibility hook is inert and `auto` can only ever
  resolve to `bm25`. Filed as
  [#45](https://github.com/cmdaltctr/llamaindex-rag-mcp/issues/45). Out of
  scope here: this change moves version bounds and must not alter runtime
  behaviour.

## Capabilities

### New Capabilities

- `dependency-floor-integrity`: the declared lower bounds in `pyproject.toml`
  form an installable, tested contract. Covers the floor policy, the
  `lowest-direct` CI gate, the drift check, and the chromadb 1.0 minimum.

### Modified Capabilities

None. No runtime behaviour changes. `architecture-boundary-enforcement`
already owns the rule that chromadb is confined to
`core/vectordb/chroma.py`, and that rule is unaffected.

## Impact

**Files**

- `pyproject.toml` — sixteen `[project.dependencies]` and
  `[project.optional-dependencies]` floors; possibly `[dependency-groups].dev`.
- `.github/workflows/ci.yml` — new `lowest-direct` job.
- `tests/` — new floor-drift test, sibling of `test_file_size_ceiling.py`.
- `docs/adr/042-*.md` and `docs/adr/ADR_README.md`.
- `uv.lock` — unchanged if the floors sit at or below the locked versions.
  Any lock churn signals a floor set above what is locked, which is a bug.

**Consumers**

Anyone installing `rag-mcp` from source without the lockfile and pinning
chromadb below 1.0, or an old llama-index, will now fail at resolution rather
than at runtime. That is the intended outcome. The commit carries a
`BREAKING CHANGE` footer, consistent with ADR-039 and ADR-040.

**Risk**

The `lowest-direct` CI job is expected to fail on first run. Floors that look
safe on paper can break in combination, and the job exists precisely to
surface that. Task ordering puts the job before the floor edits so the failing
state is observed first, matching the ADR-037 contract-before-fix pattern.

**Out of scope**

Upper caps. None exist and none are being reintroduced. Renovate or
Dependabot automation. Python version matrix changes.
