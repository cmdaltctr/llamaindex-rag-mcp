# Dependency floor evidence

Input to ADR-042 and to task group 3 (the floor edits). Every row carries the
declared floor in `pyproject.toml` today, the version resolved into `uv.lock`,
the floor this change will set, and the upstream evidence justifying it.

Locked versions were read from `uv.lock` with `tomllib`; the parent
constraints in the watch-items section were read from the installed wheels'
`METADATA` (`Requires-Dist`) and from `uv tree --invert --package <name>`.

## 1. Direct dependencies (`[project.dependencies]`)

| Package | Declared | Locked | Floor | Evidence |
| --- | --- | --- | --- | --- |
| `chromadb` | `>=0.5.0` | 1.5.9 | **`>=1.0.0`** | Migration log: 0.6.0 returns names, 1.0.0 "reverts back to returning `Collection` objects" — https://docs.trychroma.com/docs/overview/migration |
| `tree-sitter-language-pack` | `>=0.1.0` | 1.14.3 | **`>=1.12.3`** | CHANGELOG 1.12.3 + issue #157: 1.8.0–1.12.2 vendored parser, silent bad trees on 3.14, import break below 3.14 — https://github.com/xberg-io/tree-sitter-language-pack/blob/main/CHANGELOG.md |
| `tree-sitter` | `>=0.21.0` | 0.26.0 | **`>=0.23.0`** | The language pack's own PyPI `requires_dist` declares `tree-sitter>=0.23` |
| `llama-index` | `>=0.11.0` | 0.14.23 | **`>=0.14.5`** | Tightest sibling, see design D6; 0.13.0 rejected as self-inconsistent |
| `llama-index-llms-ollama` | `>=0.4.0` | 0.10.1 | **`>=0.9.0`** | First version requiring `core>=0.14.5` |
| `llama-index-vector-stores-chroma` | `>=0.2.0` | 0.5.5 | **`>=0.5.0`** | First version requiring `core>=0.13.0`; below 0.3.0 it pins `chromadb<0.6.0`, conflicting with the chromadb floor |
| `llama-index-readers-file` | `>=0.2.0` | 0.6.0 | **`>=0.5.0`** | First version requiring `core>=0.13.0` |
| `llama-index-embeddings-ollama` | `>=0.2.0` | 0.9.0 | **`>=0.7.0`** | First version requiring `core>=0.13.0` |
| `watchdog` | `>=4.0.0` | 6.0.0 | **`>=5.0.0`** | 5.0.0 renamed internal classes; the tested 6.0.0 assumes the post-rename surface |
| `networkx` | `>=3.0` | 3.6.1 | **`>=3.2`** | Modest bump past immediate post-3.0 churn; no break found through 3.6.1 |
| `onnxruntime` | `>=1.17.0` | 1.28.0 | **`>=1.20.0`** | No Python `InferenceSession` API break in range; 1.27 CUDA removal is build-time and GPU-only |
| `httpx` | `>=0.27.0` | 0.28.1 | keep | 0.28.0 removed `proxies`/`app`, neither used |
| `tokenizers` | `>=0.20` | 0.22.2 | keep | Transitive only, not imported directly; 0.21.0 break was dropping Python 3.7/3.8 |
| `typer` | `>=0.25.1` | 0.27.1 | keep | Gap too small to carry signal |
| `pyyaml` / `docx2txt` | at lock | at lock | keep | Floor already equals locked version |
| `pydantic-settings` | `>=2.14.1` | 2.15.0 | keep | One patch below locked |
| `python-dotenv` | `>=1.0.0` | 1.2.2 | keep | Stable `load_dotenv` across 1.x |
| `liteparse` | `>=2.0.0` | 2.11.1 | **keep `>=2.0.0`** | Upstream ships no formal changelog and releases near-daily, so a tighter floor is evidence-light. The wide floor is retained; the ADR records that this was a decision, not an oversight. |

### Already at floor (set by ADRs 039–041, no action needed)

| Package | Declared | Locked | Status |
| --- | --- | --- | --- |
| `mcp[cli]` | `>=2.0.0` | 2.0.0 | Floor = locked. Set by ADR-039 (mcp 2.0 upgrade). |
| `huggingface-hub` | `>=1.0.0` | 1.27.0 | Floor set by ADR-040 (huggingface-hub 1.0 upgrade). Resolves to 1.3.0 at lowest-direct due to a transitive constraint, not our floor. |

## 2. Optional dependencies (`[project.optional-dependencies]`)

Verified at task 1.3 against `uv.lock` and the installed wheels' `METADATA`.

| Package | Declared | Locked | Floor | Evidence |
| --- | --- | --- | --- | --- |
| `rank-bm25` (hybrid) | `>=0.2.2` | 0.2.2 | keep | Floor = locked. |
| `pypdfium2` (pdf-pypdfium2) | `>=4.0.0` | 5.12.1 | **keep `>=4.0.0`** | One major below locked. No known API break in the 4.x→5.x jump for the `PdfDocument` surface this project calls (`pdfium.PdfDocument`, `page.render_topil`). The wide floor is retained; the ADR records the decision. |
| `azure-ai-documentintelligence` (azure) | `>=1.0.0` | 1.0.2 | keep | Two patches below locked; no breaking change. |
| `llama-index-embeddings-openai` (llamacpp, openrouter) | `>=0.2.0` | 0.6.0 | **`>=0.5.0`** | Four minors below locked. Same core-coupling logic as the main llama-index family (design D6): 0.5.0 is the first version requiring `core>=0.13.0`, matching the rest of the family floor. |
| `llama-index-llms-openai-like` (llamacpp, openrouter) | `>=0.2.0` | 0.7.2 | **`>=0.5.0`** | Five minors below locked. Same core-coupling logic: 0.5.0+ requires `core>=0.13.0`. |
| `sentence-transformers` (torch) | `>=5.0` | 5.7.0 | keep | The existing pyproject comment defends this: v3 uses `activation_fct`, `activation_fn` did not exist until v4, v5.4+ changed persistence on `predict()`. |
| `transformers` (torch) | `>=5.0.0` | 5.15.0 | keep | Floor set by ADR-040 (coupled with huggingface-hub 1.0). |

## 3. Dev group (`[dependency-groups].dev`)

Verified at task 1.3 against `uv.lock`.

| Package | Declared | Locked | Floor | Evidence |
| --- | --- | --- | --- | --- |
| `huggingface-hub` | `>=0.36.2` | 1.27.0 | **remove** | Contradicts `[project.dependencies]`'s `>=1.0.0`. The dev entry is removed; the project dependency already covers dev. See task 3.6. |
| `import-linter` | `>=2.13` | 2.13 | keep | Floor = locked. |
| `ipywidgets` | `>=8.1.8` | 8.1.8 | keep | Floor = locked. |
| `jupytext` | `>=1.19.4` | 1.19.5 | keep | One patch below locked. |
| `openapi-spec-validator` | `>=0.7.1` | 0.9.0 | keep | Two minors below locked. Used in CI's OpenAPI validation step. The 0.7→0.9 gap adds no breaking change for the `validate()` call site. |
| `pre-commit` | `>=4.0.0` | 4.6.2 | keep | Several patches below locked but no breaking change in 4.x. |
| `pytest` | `>=9.0.3` | 9.1.1 | keep | One patch below locked. |
| `pytest-asyncio` | `>=1.3.0` | 1.4.0 | keep | One minor below locked; `asyncio_mode = "auto"` is stable across both. |
| `pytest-cov` | `>=7.1.0` | 7.1.0 | keep | Floor = locked. |
| `ruff` | `>=0.12.0` | 0.16.2 | **`>=0.16.0`** | Pre-commit runs `uv run ruff`, so a developer on the floors formats differently from CI. Four minors of drift is exactly what the drift test catches. |

## 4. Upstream-blocked transitives (ADR watch items, not floor edits)

Each is held by a parent whose own upper bound prevents the upgrade. None is
ours to move; the ADR records them so the next upgrade cycle knows what to
revisit when the parent loosens.

| Transitive | Latest on PyPI | Locked | Constraining parent | Parent's constraint |
| --- | --- | --- | --- | --- |
| `openai` | 3.0.0 | 2.54.0 | `llama-index-llms-openai` (and `llama-index-embeddings-openai`) | `openai<3,>=1.108.1` (read from installed wheel METADATA) |
| `pandas` | 3.0.5 | 2.3.3 | `llama-index-readers-file` | `pandas<3,>=2.0.0` |
| `marshmallow` | 4.3.1 | 3.26.2 | `dataclasses-json` (transitive of `llama-index-core`) | `marshmallow>=3.18.0,<4.0.0` |
| `tokenizers` | 0.23.1 | 0.22.2 | `transformers` / `sentence-transformers` (torch extra); `chromadb` declares `tokenizers>=0.13.2` with no upper bound, so the torch-extra stack is the binding constraint | upper bound inherited from the torch-extra family |
| `striprtf` | 0.0.32 | 0.0.26 | `llama-index-readers-file` | `striprtf<0.0.27,>=0.0.26` |

`pydantic-core` (locked 2.46.4, latest 2.48.0) appears in `uv pip list
--outdated` but is a transitive of `pydantic`/`pydantic-settings` and tracks
pydantic's own release cadence. Not a watch item: it moves when pydantic
moves, and there is no action for this project.
