# Task 1.4: Fresh base-wheel installation

- **Date:** 2026-08-21
- **Python:** CPython 3.12.10
- **Environment:** `/tmp/ragmcp-security-evidence-20260821/final-base-venv`
- **Installed artefact:** `rag_mcp-2.2.0-py3-none-any.whl`
- **Install mode:** Offline, wheel path only, no editable install, no extras

## Create and install

```console
$ uv venv --offline /tmp/ragmcp-security-evidence-20260821/final-base-venv
Using CPython 3.12.10
Creating virtual environment at: /tmp/ragmcp-security-evidence-20260821/final-base-venv

$ uv pip install --offline --link-mode copy \
    --python /tmp/ragmcp-security-evidence-20260821/final-base-venv/bin/python \
    /tmp/ragmcp-security-evidence-20260821/final-wheel/rag_mcp-2.2.0-py3-none-any.whl
Using Python 3.12.10 environment at: /tmp/ragmcp-security-evidence-20260821/final-base-venv
Resolved 133 packages in 198ms
Prepared 1 package in 97ms
Installed 133 packages in 2.60s
```

No package index or editable source checkout was used.

## Installed-distribution inventory check

```console
$ /tmp/ragmcp-security-evidence-20260821/final-base-venv/bin/python -c \
  '<enumerate importlib.metadata.distributions(), normalise names, and match the two Chroma names>'
installed_distribution_count=133
target_matches=[]
rag_mcp=[('rag-mcp', '2.2.0')]

$ uv pip check --python /tmp/ragmcp-security-evidence-20260821/final-base-venv/bin/python
Using Python 3.12.10 environment at: /tmp/ragmcp-security-evidence-20260821/final-base-venv
Checked 133 packages in 3ms
All installed packages are compatible
```

## Import and default-vector-store runtime check

The command used the same local Ollama provider variables as the base CI job. It did not set `VECTOR_STORE` or any `CHROMA_*` variable. This isolates the packaging assertion to the shipped default vector-store path while keeping optional cloud and llama.cpp providers out of the check.

```console
$ env EMBED_PROVIDER=local LOCAL_BACKEND=ollama EMBED_MODEL=nomic-embed-text \
    OLLAMA_BASE_URL=http://localhost:11434 METADATA_LLM_PROVIDER=local \
    PDF_READER=pypdf \
    /tmp/ragmcp-security-evidence-20260821/final-base-venv/bin/python -c \
    '<clear VECTOR_STORE and CHROMA_*; inspect imports/distributions; import compose, retrieval, ingestion; compose; search empty collection>'
python=3.12.10
chromadb_spec=None
chroma_adapter_spec=None
chromadb_distribution=False
chroma_adapter_distribution=False
torch_distribution=False
transformers_distribution=False
default_vector_store=lancedb
search_result=[]
loaded_chromadb_modules=[]
```

The import checks were:

- `importlib.util.find_spec("chromadb") is None`
- `importlib.util.find_spec("llama_index.vector_stores.chroma") is None`
- imports of `rag_mcp.compose`, `rag_mcp.core.retrieval`, and `rag_mcp.core.ingestion`
- one dense search against an empty, default-derived LanceDB collection

**Result:** PASS. Neither Chroma distribution is installed or importable. The default LanceDB path returns `[]` without loading Chroma. The base installation also remains free of PyTorch and Transformers.
