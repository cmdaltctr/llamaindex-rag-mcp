## 1. Baseline and evidence

- [x] 1.1 Record the pre-change baseline: run `uv lock --upgrade --dry-run`, `uv pip list --outdated`, and `uv lock --resolution lowest-direct --dry-run`, and save the three outputs into the change directory as `baseline.md`. This is the before-state ADR-042 cites.
- [x] 1.2 Transcribe the researched evidence table below into `evidence.md` in the change directory. It is the input to ADR-042 and to group 3.
- [x] 1.3 Verify the extras and dev-group floors, which the research pass covered only partially: `rank-bm25`, `azure-ai-documentintelligence`, `pypdfium2`, `llama-index-embeddings-openai`, `llama-index-llms-openai-like`, `import-linter`, `ipywidgets`, `jupytext`, `openapi-spec-validator`, `pre-commit`, `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`.
- [x] 1.4 List the upstream-blocked transitives with their constraining parent (openai 3.0, pandas 3.0, marshmallow 4.x, tokenizers 0.23.1, striprtf). These become ADR watch items, not floor edits.
- [x] 1.5 Open a follow-up issue for the `query_sparse` capability probe at `core/vectordb/chroma.py:390`. Filed as [#45](https://github.com/cmdaltctr/llamaindex-rag-mcp/issues/45). Do not fix it in this change.

### Researched floors (evidence for 1.2)

| Package                            | Declared   | Locked  | Floor          | Evidence                                                                                                          |
| ---------------------------------- | ---------- | ------- | -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `chromadb`                         | `>=0.5.0`  | 1.5.9   | **`>=1.0.0`**  | Migration log: 0.6.0 returns names, 1.0.0 "reverts back to returning `Collection` objects"                        |
| `tree-sitter-language-pack`        | `>=0.1.0`  | 1.14.3  | **`>=1.12.3`** | CHANGELOG 1.12.3 + issue #157: 1.8.0–1.12.2 vendored parser, silent bad trees on 3.14, import break below 3.14    |
| `tree-sitter`                      | `>=0.21.0` | 0.26.0  | **`>=0.23.0`** | The language pack's own PyPI `requires_dist` declares `tree-sitter>=0.23`                                         |
| `llama-index`                      | `>=0.11.0` | 0.14.23 | **`>=0.14.5`** | Tightest sibling, see design D6; 0.13.0 rejected as self-inconsistent                                             |
| `llama-index-llms-ollama`          | `>=0.4.0`  | 0.10.1  | **`>=0.9.0`**  | First version requiring `core>=0.14.5`                                                                            |
| `llama-index-vector-stores-chroma` | `>=0.2.0`  | 0.5.5   | **`>=0.5.0`**  | First version requiring `core>=0.13.0`; below 0.3.0 it pins `chromadb<0.6.0`, conflicting with the chromadb floor |
| `llama-index-readers-file`         | `>=0.2.0`  | 0.6.0   | **`>=0.5.0`**  | First version requiring `core>=0.13.0`                                                                            |
| `llama-index-embeddings-ollama`    | `>=0.2.0`  | 0.9.0   | **`>=0.7.0`**  | First version requiring `core>=0.13.0`                                                                            |
| `watchdog`                         | `>=4.0.0`  | 6.0.0   | **`>=5.0.0`**  | 5.0.0 renamed internal classes; the tested 6.0.0 assumes the post-rename surface                                  |
| `networkx`                         | `>=3.0`    | 3.6.1   | **`>=3.2`**    | Modest bump past immediate post-3.0 churn; no break found through 3.6.1                                           |
| `onnxruntime`                      | `>=1.17.0` | 1.28.0  | **`>=1.20.0`** | No Python `InferenceSession` API break in range; 1.27 CUDA removal is build-time and GPU-only                     |
| `httpx`                            | `>=0.27.0` | 0.28.1  | keep           | 0.28.0 removed `proxies`/`app`, neither used                                                                      |
| `tokenizers`                       | `>=0.20`   | 0.22.2  | keep           | Transitive only, not imported directly; 0.21.0 break was dropping Python 3.7/3.8                                  |
| `typer`                            | `>=0.25.1` | 0.27.1  | keep           | Gap too small to carry signal                                                                                     |
| `pyyaml` / `docx2txt`              | at lock    | at lock | keep           | Floor already equals locked version                                                                               |
| `pydantic-settings`                | `>=2.14.1` | 2.15.0  | keep           | One patch below locked                                                                                            |
| `python-dotenv`                    | `>=1.0.0`  | 1.2.2   | keep           | Stable `load_dotenv` across 1.x                                                                                   |
| `liteparse`                        | `>=2.0.0`  | 2.11.1  | decide at 1.3  | No formal changelog upstream, near-daily releases; evidence-light either way                                      |

**Already at floor (set by ADRs 039–041, no action needed):**

| Package           | Declared  | Locked | Status                                                                                                                                |
| ----------------- | --------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp[cli]`        | `>=2.0.0` | 2.0.0  | Floor = locked. Set by ADR-039 (mcp 2.0 upgrade).                                                                                     |
| `huggingface-hub` | `>=1.0.0` | 1.27.0 | Floor set by ADR-040 (huggingface-hub 1.0 upgrade). Resolves to 1.3.0 at lowest-direct due to a transitive constraint, not our floor. |
| `transformers`    | `>=5.0.0` | 5.15.0 | Floor set by ADR-040 (coupled with huggingface-hub 1.0). In the `torch` extra only.                                                   |
| `rank-bm25`       | `>=0.2.2` | 0.2.2  | Floor = locked. In the `hybrid` extra.                                                                                                |

**Extras and dev-group (verify at task 1.3):**

| Package                         | Declared   | Locked | Floor             | Evidence                                                                                                                                                                            |
| ------------------------------- | ---------- | ------ | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sentence-transformers`         | `>=5.0`    | 5.7.0  | keep              | The existing pyproject comment defends this: v3 uses `activation_fct`, `activation_fn` did not exist until v4, v5.4+ changed persistence on `predict()`. In the `torch` extra only. |
| `pypdfium2`                     | `>=4.0.0`  | 5.12.1 | **decide at 1.3** | One major below locked. In the `pdf-pypdfium2` extra. No known API break in the 4.x→5.x jump for the `PdfDocument` surface this project calls.                                      |
| `azure-ai-documentintelligence` | `>=1.0.0`  | 1.0.2  | keep              | Two patches below locked; no breaking change. In the `azure` extra.                                                                                                                 |
| `llama-index-embeddings-openai` | `>=0.2.0`  | 0.6.0  | **decide at 1.3** | Four minors below locked. In the `llamacpp` and `openrouter` extras. Same core-coupling logic as the main llama-index family (design D6).                                           |
| `llama-index-llms-openai-like`  | `>=0.2.0`  | 0.7.2  | **decide at 1.3** | Five minors below locked. In the `llamacpp` and `openrouter` extras. Same core-coupling logic.                                                                                      |
| `ruff`                          | `>=0.12.0` | 0.16.2 | **`>=0.16.0`**    | Pre-commit runs `uv run ruff`, so a developer on the floors formats differently from CI. Four minors of drift is exactly what the drift test catches.                               |
| `pytest`                        | `>=9.0.3`  | 9.1.1  | keep              | One patch below locked.                                                                                                                                                             |
| `pre-commit`                    | `>=4.0.0`  | 4.6.2  | keep              | Several patches below locked but no breaking change in 4.x.                                                                                                                         |
| `import-linter`                 | `>=2.13`   | 2.13   | keep              | Floor = locked.                                                                                                                                                                     |
| `openapi-spec-validator`        | `>=0.7.1`  | 0.9.0  | **decide at 1.3** | Two minors below locked. Used in CI's OpenAPI validation step.                                                                                                                      |
| `pytest-asyncio`                | `>=1.3.0`  | 1.4.0  | keep              | One minor below locked; `asyncio_mode = "auto"` is stable across both.                                                                                                              |
| `pytest-cov`                    | `>=7.1.0`  | 7.1.0  | keep              | Floor = locked.                                                                                                                                                                     |
| `ipywidgets`                    | `>=8.1.8`  | 8.1.8  | keep              | Floor = locked.                                                                                                                                                                     |
| `jupytext`                      | `>=1.19.4` | 1.19.5 | keep              | One patch below locked.                                                                                                                                                             |

## 2. Guardrails first (expected to fail)

- [x] 2.1 Add `tests/test_dependency_floors.py` mirroring `tests/test_file_size_ceiling.py`: stdlib only, `tomllib` for both `pyproject.toml` and `uv.lock`, no fixtures, reports every offender rather than the first.
- [x] 2.2 Implement the drift assertion: fail when a declared floor sits more than one minor below its locked version, listing package, declared floor, and locked version.
- [x] 2.3 Implement the inverse assertion: fail when a declared floor sits above its locked version, since the lockfile would then violate the declared contract.
- [x] 2.4 Cover all three dependency tables in the test: `[project.dependencies]`, every group in `[project.optional-dependencies]`, and `[dependency-groups].dev`.
- [x] 2.5 Verify the test fails on the current tree, and record which packages it names. Per design D4 this failing state is the point.
- [x] 2.6 Verify the test actually tests: temporarily set one floor to its locked version and confirm that package drops out of the failure list.
- [x] 2.7 Add the `floors` job to `.github/workflows/ci.yml`: checkout, setup-python 3.12, setup-uv, `uv sync --resolution lowest-direct`, then `uv run --no-sync pytest -m "not slow" --tb=short -q`. Pin every action to a SHA, matching the existing jobs.
- [x] 2.8 Set the same environment variables the existing `test` job uses (`PDF_READER=pypdf`, `EMBED_PROVIDER=local`, `LOCAL_BACKEND=ollama`, `EMBED_MODEL=nomic-embed-text`, `OLLAMA_BASE_URL`, `METADATA_LLM_PROVIDER=local`) so the floor job and the normal job differ only in resolution strategy.
- [x] 2.9 Do not suppress failures with `|| echo`. The job must be able to go red.
- [x] 2.10 Run the floor job's commands locally against a scratch virtualenv, so the first CI run is not the first time anyone has seen the result. Restore `uv.lock` afterwards.
- [x] 2.11 Record which floors actually break, and reconcile that list against the predictions from 1.2. Any divergence updates the evidence table before the floors move.

## 3. Raise the floors

- [x] 3.1 Raise `chromadb` to `>=1.0.0`, with an inline comment naming the 0.6.0–0.9.x `list_collections` regression and linking the migration log.
- [x] 3.2 Raise the llama-index set together: `llama-index>=0.14.5`, `llama-index-llms-ollama>=0.9.0`, `llama-index-vector-stores-chroma>=0.5.0`, `llama-index-readers-file>=0.5.0`, `llama-index-embeddings-ollama>=0.7.0`. Add one comment above the group explaining the coupling and why the floor follows the tightest sibling (design D6), in the style of the existing mcp and huggingface-hub comments.
- [x] 3.3 Raise the AST stack: `tree-sitter-language-pack>=1.12.3` and `tree-sitter>=0.23.0`. Comment the silent-failure mode, since a reader would otherwise assume this is a routine bump.
- [x] 3.4 Raise `watchdog>=5.0.0`, `networkx>=3.2`, `onnxruntime>=1.20.0`. Leave `httpx`, `tokenizers`, `typer`, `pyyaml`, `pydantic-settings`, `python-dotenv`, and `docx2txt` unchanged, and record in the ADR that leaving them was a decision rather than an oversight.
- [x] 3.4a Decide `liteparse` per task 1.3. Upstream ships no formal changelog and releases near-daily, so `>=2.0.0` is evidence-light. Either pin close to the tested 2.11.1 or keep the wide floor, and say which in the ADR.
- [x] 3.5 Raise the extras floors: `pypdfium2` (declared `>=4.0.0`, locked 5.12.1), `llama-index-embeddings-openai`, `llama-index-llms-openai-like`, `azure-ai-documentintelligence`, `rank-bm25`, `sentence-transformers`.
- [x] 3.6 Fix the dev-group contradiction: `[dependency-groups].dev` declares `huggingface-hub>=0.36.2` while `[project.dependencies]` declares `>=1.0.0`. Remove the dev entry or align it, and say which in the ADR.
- [x] 3.7 Raise the remaining dev floors where they affect reproducibility, in particular `ruff` (declared `>=0.12.0`, locked 0.16.2). Pre-commit runs `uv run ruff`, so a developer on the floors formats differently from CI. Also review `pre-commit`, `pytest`, `pytest-asyncio`, `pytest-cov`, `openapi-spec-validator`, `jupytext`, `import-linter`.
- [x] 3.8 Confirm `uv.lock` is byte-identical after `uv sync`. Any churn means a floor was set above its locked version.
- [x] 3.9 Confirm the drift test from group 2 now passes.

## 4. Verification

- [x] 4.1 `uv sync` then `uv run pytest -m "not slow" --cov=rag_mcp --cov-branch` — full fast suite green, coverage at or above the current 92%.
- [x] 4.2 `uv run lint-imports` — all six import-linter contracts pass.
- [x] 4.3 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [x] 4.4 `openspec validate --all --strict` passes.
- [x] 4.5 Run the floor job's command sequence locally one final time and confirm it is green.
- [x] 4.6 Verify the torch extra still installs and its tests pass, since `sentence-transformers` and `transformers` floors sit in that extra.
- [x] 4.6a Run the codebase-map and AST tests explicitly against the floor install. Per design D7, a package-level smoke test would pass while `get_parser()` returns a broken parser, so this path needs real assertions on extracted symbols.
- [x] 4.7 Confirm the default install stays torch-free, matching the existing CI guard (ADR-038).

## 5. Documentation

- [x] 5.1 Write `docs/adr/042-dependency-floor-integrity.md`: context, the floor policy from design D1, the per-package evidence table from 1.2, the `lowest-direct` gate decision from D2, and alternatives considered.
- [x] 5.2 Record the upstream-blocked transitives from 1.4 as ADR watch items, each naming its constraining parent.
- [x] 5.3 Record both concrete failures the change prevents, with code references and their different detection costs (design D7): the chromadb 0.6.0–0.9.x `AttributeError` at `core/vectordb/chroma.py`, and the tree-sitter-language-pack 1.8.0–1.12.2 silent AST degradation at `core/codebase/ast_extract.py`.
- [x] 5.3a Record the rejected `llama-index>=0.13.0` alternative and why the floor follows the tightest sibling, so a future reader does not lower it back.
- [x] 5.4 Add ADR-042 to `docs/adr/ADR_README.md`.
- [x] 5.5 Grep `docs/guides/` for any stated minimum versions and update them. The AGENTS.md documentation-drift check applies here.
- [x] 5.6 Add a line to AGENTS.md noting that dependency floors are enforced by `tests/test_dependency_floors.py` and the `floors` CI job, so the next upgrade cycle finds the rule.

## 6. Ship

- [x] 6.1 Commit as `chore(deps)!: raise dependency floors to tested versions`, with a `BREAKING CHANGE` footer naming each package and its new minimum.
- [x] 6.2 Open the PR against `v3`, not `main`.
- [ ] 6.3 Confirm all CI jobs green, including the new `floors` job.
- [ ] 6.4 Archive the change with `openspec archive raise-dependency-floors`.
