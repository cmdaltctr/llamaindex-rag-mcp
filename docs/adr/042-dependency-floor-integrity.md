# ADR-042: Dependency Floor Integrity

**Date:** 2026-08-12
**Status:** Accepted
**Scopes:** ADR-039 (mcp 2.0), ADR-040 (huggingface-hub 1.0), ADR-041 (onnxruntime 1.28)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The major dependency upgrade cycle (ADRs 039–041) lifted every upper cap in
`pyproject.toml`. The lockfile now resolves at ceiling: `uv lock --upgrade`
reports no changes. The lower bounds were never touched. Sixteen of them sat
one or more majors below the versions the test suite actually exercises, and
CI installs with `uv sync --frozen`, so no job had ever run the declared
floors.

Two of those floors were not merely stale, they were wrong:

1. **chromadb** `>=0.5.0` admitted the entire 0.6.0–0.9.x range, where
   `list_collections()` returns collection names as strings instead of
   `Collection` objects. `ChromaVectorStoreAdapter.list_collections` at
   `src/rag_mcp/core/vectordb/chroma.py:119` does
   `[c.name for c in client.list_collections()]` and raises
   `AttributeError: 'str' object has no attribute 'name'` across that whole
   range. Chroma's migration log records the break at v0.6.0 (2024-12-30)
   and the revert at v1.0.0 (2025-03-01).
   <https://docs.trychroma.com/docs/overview/migration>

2. **tree-sitter-language-pack** `>=0.1.0` sat nine majors below the locked
   1.14.3 and admitted 1.8.0 through 1.12.2, where `get_parser()` returned a
   vendored parser class rather than `tree_sitter.Parser`. On Python 3.14
   the vendored parser "produced unusable trees … while nothing failed at
   construction, so the breakage was silent", and on Python below 3.14 an
   invalid `_rust.Parser` return annotation "broke import"
   (<https://github.com/xberg-io/tree-sitter-language-pack/blob/main/CHANGELOG.md>,
   issue #157). `ast_extract.py` calls `get_parser(lang)` then
   `parser.parse(content_bytes)` inside a broad `try/except`, so the silent
   variant degraded every AST extraction to a logged warning per file rather
   than a visible failure. The project declares `requires-python = ">=3.11"`,
   so both variants are inside the supported matrix.

Running `uv lock --resolution lowest-direct` showed what the declared
contract resolved to today: chromadb 0.5.17, tree-sitter-language-pack 0.1.0
(unbuildable — missing `src/parsers` directory), tree-sitter 0.22.0,
networkx 3.0, onnxruntime 1.17.0, watchdog 4.0.0, llama-index-llms-ollama
0.7.2. That stack had never been installed, never been tested, and was not
what the project supports. The pre-change baseline is recorded in
`openspec/changes/raise-dependency-floors/baseline.md`.

## Decision

### Floor policy (design D1)

**Floor = lowest version proven safe against the project's actual API usage,
not the locked version.**

The alternative — floor = locked version — is a lie in the opposite
direction. It claims the project breaks on versions it demonstrably works
on, and it forces a floor bump on every routine minor upgrade, which makes
the `BREAKING CHANGE` footer meaningless through repetition.

The research pass asked one question per package: what is the earliest
release that still provides the API this project calls? Where the answer is
genuinely "the locked version", the floor goes there and this ADR says why.
Where a package has had no relevant breaking change in years (`networkx`,
`pyyaml`, `python-dotenv`), the floor moves conservatively, or not at all.

`chromadb` is the exception that proves the rule. Its floor is set by an
observed regression, not by the lock: 0.6.0 changed `list_collections()` to
return strings, 1.x returns `Collection` objects again. The floor is the
version that restored the object return.

### Gate with `--resolution lowest-direct` (design D2)

A CI job (`floors`) installs with `uv sync --resolution lowest-direct` and
runs the fast test suite. This converts the floors from a comment into a
tested contract. Without it they rot again on the next upgrade cycle.

Rejected alternative: a committed `uv-lowest.lock`. It is a second artefact
to keep current and it goes stale exactly like the floors it guards.

### Drift check as a test (design D3)

`tests/test_dependency_floors.py` reads floors from `pyproject.toml` and
versions from `uv.lock`, both with stdlib `tomllib`, and fails when a floor
sits more than one minor below its locked version, or above it. Mirrors
`tests/test_file_size_ceiling.py`: stdlib only, no fixtures, reports every
offender rather than the first.

The "one minor" tolerance is deliberate. Zero tolerance would force a floor
bump on every routine patch upgrade and make the check noise. Two or more
minors of drift is the point at which "supported" and "tested" have visibly
diverged.

Packages exempt from the one-minor rule are listed in the test with a
comment naming the reason, so they are reviewable. A silent skip list is how
the floors rotted in the first place.

### Per-package evidence table

The full evidence table is in
`openspec/changes/raise-dependency-floors/evidence.md`. Summary of the
raises:

| Package | Old floor | New floor | Evidence |
| --- | --- | --- | --- |
| `chromadb` | `>=0.5.0` | `>=1.0.0` | Migration log: 0.6.0 returns names, 1.0.0 reverts to `Collection` objects |
| `tree-sitter-language-pack` | `>=0.1.0` | `>=1.12.3` | CHANGELOG 1.12.3 + issue #157: silent bad trees on 3.14, import break below 3.14 |
| `tree-sitter` | `>=0.21.0` | `>=0.23.0` | The language pack's own `requires_dist` declares `tree-sitter>=0.23` |
| `llama-index` | `>=0.11.0` | `>=0.14.5` | Tightest sibling (design D6); 0.13.0 rejected as self-inconsistent |
| `llama-index-llms-ollama` | `>=0.4.0` | `>=0.9.0` | First version requiring `core>=0.14.5` |
| `llama-index-vector-stores-chroma` | `>=0.2.0` | `>=0.5.0` | First version requiring `core>=0.13.0`; below 0.3.0 pins `chromadb<0.6.0` |
| `llama-index-readers-file` | `>=0.2.0` | `>=0.5.0` | First version requiring `core>=0.13.0` |
| `llama-index-embeddings-ollama` | `>=0.2.0` | `>=0.7.0` | First version requiring `core>=0.13.0` |
| `llama-index-embeddings-openai` | `>=0.2.0` | `>=0.5.0` | Same core-coupling logic (D6) |
| `llama-index-llms-openai-like` | `>=0.2.0` | `>=0.5.0` | Same core-coupling logic (D6) |
| `watchdog` | `>=4.0.0` | `>=5.0.0` | 5.0.0 renamed internal classes |
| `networkx` | `>=3.0` | `>=3.2` | Modest bump past post-3.0 churn |
| `onnxruntime` | `>=1.17.0` | `>=1.20.0` | No `InferenceSession` API break in range |
| `ruff` (dev) | `>=0.12.0` | `>=0.16.0` | Pre-commit runs `uv run ruff`; floor drift causes format divergence |

Packages left unchanged (a decision, not an oversight): `httpx`, `tokenizers`,
`typer`, `pyyaml`, `pydantic-settings`, `python-dotenv`, `docx2txt`,
`liteparse`, `pypdfium2`, `azure-ai-documentintelligence`, `rank-bm25`,
`sentence-transformers`, `transformers`, `pre-commit`, `pytest`,
`pytest-asyncio`, `pytest-cov`, `openapi-spec-validator`, `jupytext`,
`import-linter`, `ipywidgets`.

`liteparse` (`>=2.0.0`, locked 2.11.1): upstream ships no formal changelog
and releases near-daily, so `>=2.0.0` is evidence-light. A tighter floor
would be a guess. The wide floor is retained.

`pypdfium2` (`>=4.0.0`, locked 5.12.1): no known API break in the 4.x→5.x
jump for the `PdfDocument` surface this project calls. The wide floor is
retained.

### Dev-group contradiction fixed

`[dependency-groups].dev` declared `huggingface-hub>=0.36.2` while
`[project.dependencies]` declared `>=1.0.0`. The dev entry was removed —
the project dependency already covers dev.

### The `llama-index` floor follows the tightest sibling (design D6)

The research pass surfaced a contradiction inside the family. Reading PyPI
`requires_dist` at each historical version:

| Package | Earliest version needing core 0.13.0 | What the locked version needs |
| --- | --- | --- |
| `llama-index-vector-stores-chroma` | 0.5.0 | `core>=0.13.0,<0.15` |
| `llama-index-readers-file` | 0.5.0 | `core>=0.13.0,<0.15` |
| `llama-index-embeddings-ollama` | 0.7.0 | `core>=0.13.0,<0.15` |
| `llama-index-llms-ollama` | 0.7.0, then **0.9.0 jumps to core>=0.14.5** | `core>=0.14.5,<0.15` |

Answering "earliest core compatible with the chroma adapter" gives 0.13.0.
Answering "earliest core the whole locked family can share" gives 0.14.5.
Declaring 0.13.0 would mean the stated floors only work because the resolver
happens to pick newer patches, which is precisely the class of accident
this change exists to remove.

Chosen: `llama-index>=0.14.5`, with `llama-index-llms-ollama>=0.9.0` as the
sibling that sets it. Floors must be self-consistent when read alone.

### Two concrete failures prevented, with different detection costs (D7)

Both broken floors get the same treatment, but this ADR does not flatten
them into one story, because the detection cost differs.

`chromadb` 0.6.0 to 0.9.x fails loudly. `AttributeError` on `.name`, first
call to `list_collections()`, immediately visible at
`src/rag_mcp/core/vectordb/chroma.py:119`.

`tree-sitter-language-pack` 1.8.0 to 1.12.2 fails quietly on Python 3.14.
The vendored parser constructed fine and produced unusable trees, and
`ast_extract.py` wraps the call in a broad `except Exception`, so the
symptom is a logged warning per file and a silently empty code graph at
`src/rag_mcp/core/codebase/ast_extract.py`. On Python below 3.14 the same
range broke at import instead. The project's `requires-python = ">=3.11"`
spans both.

The design consequence: the `floors` CI job runs the full fast suite,
including the AST tests, not just a package-import smoke test. A smoke test
that only checks the package imports would pass on Python 3.14 while the
parser returns rubbish.

### Upstream-blocked transitives (watch items)

Each is held by a parent whose own upper bound prevents the upgrade. None
is ours to move; revisit when the parent loosens.

| Transitive | Latest | Locked | Constraining parent | Parent's constraint |
| --- | --- | --- | --- | --- |
| `openai` | 3.0.0 | 2.54.0 | `llama-index-llms-openai`, `llama-index-embeddings-openai` | `openai<3,>=1.108.1` |
| `pandas` | 3.0.5 | 2.3.3 | `llama-index-readers-file` | `pandas<3,>=2.0.0` |
| `marshmallow` | 4.3.1 | 3.26.2 | `dataclasses-json` (transitive of `llama-index-core`) | `marshmallow>=3.18.0,<4.0.0` |
| `tokenizers` | 0.23.1 | 0.22.2 | `transformers` / `sentence-transformers` (torch extra) | upper bound from torch-extra family |
| `striprtf` | 0.0.32 | 0.0.26 | `llama-index-readers-file` | `striprtf<0.0.27,>=0.0.26` |

## Alternatives considered

- **Floor = locked version.** Rejected (design D1). It claims the project
  breaks on versions it demonstrably works on, and forces a floor bump on
  every routine minor upgrade, making the `BREAKING CHANGE` footer
  meaningless through repetition.

- **Committed `uv-lowest.lock`.** Rejected (design D2). It is a second
  artefact to keep current and it goes stale exactly like the floors it
  guards. It recreates the problem one level up.

- **Pre-commit hook for drift.** Rejected (design D3). Hooks are skippable
  with `--no-verify` and do not run in CI, so the invariant would hold only
  for developers who remembered to install them. The file-size ceiling made
  this call already.

- **`llama-index>=0.13.0`.** Rejected (design D6). Declaring 0.13.0 would
  mean the stated floors only work because the resolver happens to pick
  newer patches. The floor follows the tightest sibling (0.14.5) so it is
  self-consistent when read alone.

## Consequences

- **Positive:** the declared floors now describe an installable, tested
  contract. The `floors` CI job proves it on every push. The drift test
  catches future rot at review time. Two concrete bugs (chromadb
  `list_collections` regression, tree-sitter silent AST degradation) are
  excluded at resolution rather than discovered at runtime.
- **Negative:** consumers pinned to old chromadb or llama-index now fail at
  resolution rather than at runtime. That is the intended outcome — they
  failed at runtime before; failing at resolution is strictly better.
- **Neutral:** `uv.lock` resolved versions are unchanged. The lockfile's
  specifier metadata for the `rag-mcp` package entry updates to reflect the
  new floors, but no package version moves.

## Verification

- `uv run pytest -m "not slow" --cov=rag_mcp --cov-branch`: **1202 passed,
  3 skipped**, coverage 91% (branch; equivalent to ~93–94% line-only).
- `uv run lint-imports`: 6 contracts kept, 0 broken.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `openspec validate --all --strict`: 34 passed, 0 failed.
- Floor job (`uv sync --resolution lowest-direct` + fast suite in scratch
  venv): **1202 passed, 3 skipped**.
- AST tests at floor install (`tests/unit/test_codebase_map.py`,
  `test_code_graph.py`, `test_codebase_map_integration.py`): **60 passed**.
- Torch extra at floor install: **6 passed** (slow, `torch or
  backend_contract`).
- Default install torch-free: confirmed.
- `tests/test_dependency_floors.py`: passes.

## References

- Proposal: `openspec/changes/raise-dependency-floors/proposal.md`
- Design: `openspec/changes/raise-dependency-floors/design.md`
- Evidence: `openspec/changes/raise-dependency-floors/evidence.md`
- Baseline: `openspec/changes/raise-dependency-floors/baseline.md`
- Drift test: `tests/test_dependency_floors.py`
- CI job: `.github/workflows/ci.yml` (`floors` job)
- Chroma migration log: <https://docs.trychroma.com/docs/overview/migration>
- tree-sitter-language-pack CHANGELOG:
  <https://github.com/xberg-io/tree-sitter-language-pack/blob/main/CHANGELOG.md>
