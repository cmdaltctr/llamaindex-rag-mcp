# Design D9: Chroma server entry-point check

- **Date:** 2026-08-21
- **Scope:** `src/rag_mcp/**/*.py`
- **Structural scanner:** `ast-grep 0.45.1`

## Negative launch checks

```console
$ ast-grep run --pattern 'uvicorn.run($$$)' --lang python --json src/rag_mcp
[]

$ ast-grep run --pattern 'FastAPI($$$)' --lang python --json src/rag_mcp
[]
```

A source text search for the following regular expression also returned zero matches:

```text
chromadb\.app|FastAPI|uvicorn|chromadb.*run\(
```

This covers direct imports of `chromadb.app`, FastAPI construction, `uvicorn` imports or launch calls, and a Chroma-qualified `run(...)` call.

## Positive client-construction checks

The only structural Chroma client constructors found were:

```text
src/rag_mcp/core/vectordb/chroma.py:113
    chromadb.PersistentClient(path=persist_dir)

src/rag_mcp/core/vectordb/chroma.py:403
    chromadb.CloudClient(**kwargs)

src/rag_mcp/core/vectordb/chroma.py:465
    chromadb.PersistentClient(path=_resolve_local_persist_dir(persist_dir))
```

`PersistentClient` opens local embedded storage. `CloudClient` connects to the opt-in hosted service. No project production path starts Chroma's Python FastAPI server.

## Quick secret-leakage review

- `core/vectordb/legacy.py` includes the configured legacy directory in operator diagnostics. It does not read or print credentials.
- `core/vectordb/registry.py` exposes backend names, required modules and distributions, extra names, and install guidance. It carries no secret value.
- The reviewed Chroma cloud construction path passes the API key to `CloudClient` and applies `redact_cloud_secrets(...)` to connection errors.

**Result:** PASS. The residual server advisory path is not launched by this project's source entry points. This reachability result does not accept or clear the universal-lock advisory; design D9 still requires the policy-owner disposition.
