# src/omrg/core/vectordb (vector stores)

The store contract and one folder per backend.

## What belongs here

- The shared contract at this level: `base.py`, `identity.py`, `legacy.py`, `naming.py`, `registry.py`, `score.py`, `summary.py` and `validation.py`.
- LanceDB code in `lancedb/`. Chroma code in `chroma/` (optional `chroma` extra).

## What it must not import

- `lancedb` outside `lancedb/`, and `chromadb` outside `chroma/` (contracts `lancedb-confined-to-vectordb` and `chromadb-confined-to-vectordb`).
- `legacy.py` never imports `chromadb`. It runs in every install.

## Rules

1. Put backend code in its backend folder. `tests/unit/test_folder_layout.py` fails otherwise.
2. Keep each backend `__init__.py` free of imports. There is no re-export shim.
3. Add a backend with one folder and one `register()` call in `registry.py`. Use `module:attr` strings.
4. A new SDK import site needs an exact `ignore_imports` entry in `pyproject.toml`.
5. Every backend passes `tests/test_vectordb_contract.py`. Chroma tests skip without the extra. CI runs them in the chroma-extra job.
6. Keep each file under 500 lines.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Architecture guide](../../../../docs/guides/architecture.md)
