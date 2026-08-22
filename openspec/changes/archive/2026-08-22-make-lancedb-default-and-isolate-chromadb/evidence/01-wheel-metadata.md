# Task 1.3: Base wheel metadata

- **Date:** 2026-08-21
- **Build tool:** `uv 0.8.4 (e176e1714 2025-07-30)`
- **Build mode:** Wheel only, offline, no extras selected
- **Wheel:** `rag_mcp-2.2.0-py3-none-any.whl`
- **SHA-256:** `32a00c7f257e79f6342b53712555be4a2f88ade6080dffb2335d9ae8c8f7f690`
- **Build-input SHA-256:** `8a10e89ca3fbe3e86cb368a7888003fdc717adcb69b00f7e2deeae8b383a8d7b` across `pyproject.toml` and 126 packaged source/configuration files
- **Metadata member:** `rag_mcp-2.2.0.dist-info/METADATA`

## Build command and output

```console
$ uv build --wheel --offline --out-dir /tmp/ragmcp-security-evidence-20260821/final-wheel
Building wheel...
Successfully built /tmp/ragmcp-security-evidence-20260821/final-wheel/rag_mcp-2.2.0-py3-none-any.whl
```

## Relevant `Requires-Dist` lines

```text
Requires-Dist: chromadb>=1.0.0; extra == 'chroma'
Requires-Dist: llama-index-vector-stores-chroma>=0.5.0; extra == 'chroma'
```

The metadata inspection found two target requirements and zero unconditional target requirements. Both Chroma distributions are guarded by `extra == 'chroma'`.

**Result:** PASS. The built base wheel does not declare `chromadb` or `llama-index-vector-stores-chroma` as an unconditional dependency.
