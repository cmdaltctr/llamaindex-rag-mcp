# Pre-change baseline

Captured at the start of the `raise-dependency-floors` change, before any
floor in `pyproject.toml` was edited. This is the before-state ADR-042 cites.

All three commands ran against the same tree (commit preceding
`chore(deps)!: raise dependency floors to tested versions`).

## `uv lock --upgrade --dry-run`

Confirms the lockfile is at ceiling: every upper cap is lifted and there is
nothing newer to resolve to. This change moves only lower bounds, so this
output is expected to stay the same after the floor edits.

```
Resolved 234 packages in 1.26s
No lockfile changes detected
```

## `uv pip list --outdated`

Lists packages whose installed version is below the latest available on PyPI.
The five entries that are not ours to move — `openai`, `pandas`,
`marshmallow`, `tokenizers`, `striprtf` — are upstream-blocked transitives
(see `evidence.md` watch items). `pydantic-core` is a transitive of
`pydantic-settings` and tracks pydantic's own release cadence.

```
Package       Version Latest Type
------------- ------- ------ -----
marshmallow   3.26.2  4.3.1  wheel
openai        2.54.0  3.0.0  wheel
pandas        2.3.3   3.0.5  wheel
pydantic-core 2.46.4  2.48.0 wheel
striprtf      0.0.26  0.0.32 wheel
tokenizers    0.22.2  0.23.1 wheel
```

## `uv lock --resolution lowest-direct --dry-run`

What the declared contract resolves to today, if anyone installed without the
lockfile. This is the stack the `floors` CI job will install. It has never been
tested. The output is the diff against the committed `uv.lock`.

Notable points:

- `chromadb v1.5.9 -> v0.5.17` — the regression range is wide open.
- `tree-sitter-language-pack v1.14.3 -> v0.1.0` — nine majors of drift.
- `tree-sitter v0.26.0 -> v0.22.0` — below the language pack's own minimum.
- `llama-index v0.14.23 -> v0.14.4` and the whole llama-index family drop
  to versions that pre-date the `core>=0.14.5` contract.
- `watchdog v6.0.0 -> v4.0.0`, `networkx v3.6.1 -> v3.0`,
  `onnxruntime v1.28.0 -> v1.17.0` — the routine-stale floors.
- `ruff v0.16.2 -> v0.12.0` — four minors of drift on the formatter that
  pre-commit runs.

```
Ignoring existing lockfile due to change in resolution mode: `highest` vs. `lowest-direct`
Resolved 257 packages in 434ms
Add asgiref v3.12.1
Update azure-ai-documentintelligence v1.0.2 -> v1.0.0
Add backoff v2.2.1
Add chroma-hnswlib v0.7.6
Update chromadb v1.5.9 -> v0.5.17
Add coloredlogs v15.0.1
Add fastapi v0.141.1
Update httpx v0.28.1 -> v0.27.0
Update huggingface-hub v1.27.0 -> v1.3.0
Add humanfriendly v10.0
Update jsonschema-path v0.5.0 -> v0.3.4
Update jupytext v1.19.5 -> v1.19.4
Update liteparse v2.11.1 -> v2.0.0
Add llama-cloud v1.6.0
Update llama-index v0.14.23 -> v0.14.4
Add llama-index-cli v0.5.5
Update llama-index-embeddings-ollama v0.9.0 -> v0.8.3
Update llama-index-embeddings-openai v0.6.0 -> v0.5.1
Add llama-index-indices-managed-llama-cloud v0.11.1
Update llama-index-llms-ollama v0.10.1 -> v0.7.2
Update llama-index-llms-openai v0.7.10 -> v0.6.26
Update llama-index-llms-openai-like v0.7.2 -> v0.6.0
Update llama-index-readers-file v0.6.0 -> v0.5.4
Add llama-index-readers-llama-parse v0.6.1
Update llama-index-vector-stores-chroma v0.5.5 -> v0.5.3
Add llama-parse v0.5.20
Update networkx v3.6.1 -> v3.0
Update onnxruntime v1.28.0 -> v1.17.0
Update openapi-schema-validator v0.9.0 -> v0.6.3
Update openapi-spec-validator v0.9.0 -> v0.7.1
Add opentelemetry-instrumentation v0.65b0
Add opentelemetry-instrumentation-asgi v0.65b0
Add opentelemetry-instrumentation-fastapi v0.65b0
Add opentelemetry-util-http v0.65b0
Update pandas v2.3.3 -> v2.2.3
Update pathable v0.6.0 -> v0.4.4
Add posthog v7.38.4
Update pre-commit v4.6.2 -> v4.0.0
Remove pybase64 v1.5.0
Update pydantic-settings v2.15.0 -> v2.14.1
Update pypdfium2 v5.12.1 -> v4.0.0
Add pyreadline3 v3.5.6
Update pytest v9.1.1 -> v9.0.3
Update pytest-asyncio v1.4.0 -> v1.3.0
Update python-dotenv v1.2.2 -> v1.0.0
Update referencing v0.37.0 -> v0.36.2
Update ruff v0.16.2 -> v0.12.0
Update sentence-transformers v5.7.0 -> v5.2.0
Update tokenizers v0.22.2 -> v0.22.1
Update transformers v5.15.0 -> v5.0.0
Update tree-sitter v0.26.0 -> v0.22.0
Add tree-sitter-c-sharp v0.23.5
Add tree-sitter-embedded-template v0.25.0
Update tree-sitter-language-pack v1.14.3 -> v0.1.0
Add tree-sitter-php v0.24.1
Add tree-sitter-typescript v0.23.2
Add tree-sitter-xml v0.7.0
Add tree-sitter-yaml v0.7.2
Update typer v0.27.1 -> v0.25.1
Add typer-slim v0.24.0
Update watchdog v6.0.0 -> v4.0.0
```
