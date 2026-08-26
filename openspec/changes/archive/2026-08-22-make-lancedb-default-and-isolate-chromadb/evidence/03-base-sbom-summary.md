# Task 1.5: Base artefact and fresh-install scan

- **Date:** 2026-08-21
- **Scanner:** `pip-audit 2.10.1`
- **Vulnerability service:** PyPI advisory service, the scanner default
- **Wheel:** `rag_mcp-2.2.0-py3-none-any.whl`
- **Wheel SHA-256:** `32a00c7f257e79f6342b53712555be4a2f88ade6080dffb2335d9ae8c8f7f690`
- **Complete scanner JSON:** [`03-base-sbom.json`](03-base-sbom.json)
- **Scanner JSON SHA-256:** `0f1f118865080c58a49a987ebe7a1c2bfe8389d031e48a1c3f796645a8f094fd`

## Scanner invocation compatibility

The suggested positional wheel form is unsupported by `pip-audit 2.10.1`:

```console
$ uvx pip-audit /tmp/ragmcp-security-evidence-20260821/final-wheel/rag_mcp-2.2.0-py3-none-any.whl --format json
ERROR:pip_audit._cli:couldn't find a supported project file in /tmp/ragmcp-security-evidence-20260821/final-wheel/rag_mcp-2.2.0-py3-none-any.whl
```

A requirements-file wrapper also failed before advisory lookup because the scanner's temporary environment aborted during `ensurepip`:

```text
subprocess.CalledProcessError: Command '[.../python3.12', '-m', 'ensurepip', '--upgrade', '--default-pip']' died with <Signals.SIGABRT: 6>.
```

The successful method installed the named wheel offline into a dedicated scan environment. `pip-audit --path` then scanned the resulting site-packages directory. This keeps the scan tied to the built artefact and avoids the failing scanner-owned temporary environment.

## Scan A: built-wheel dependency closure

```console
$ uv venv --offline /tmp/ragmcp-security-evidence-20260821/final-wheel-scan-venv
$ uv pip install --offline --link-mode copy \
    --python /tmp/ragmcp-security-evidence-20260821/final-wheel-scan-venv/bin/python \
    /tmp/ragmcp-security-evidence-20260821/final-wheel/rag_mcp-2.2.0-py3-none-any.whl
Resolved 133 packages in 176ms
Prepared 1 package in 89ms
Installed 133 packages in 2.55s

$ uvx pip-audit \
    --path /tmp/ragmcp-security-evidence-20260821/final-wheel-scan-venv/lib/python3.12/site-packages \
    --format json --progress-spinner off
exit_code=0
dependencies=133
vulnerabilities=0
fixes=0
```

## Scan B: independently created fresh installation

```console
$ uvx pip-audit \
    --path /tmp/ragmcp-security-evidence-20260821/final-base-venv/lib/python3.12/site-packages \
    --format json --progress-spinner off
exit_code=0
dependencies=133
vulnerabilities=0
fixes=0
```

The two scans used separate virtual environments and separate scanner invocations. Their complete JSON outputs were byte-identical. `03-base-sbom.json` preserves that exact shared payload.

`pip-audit` records the local, unpublished `rag-mcp` distribution as unavailable on PyPI and therefore not auditable by name. It audited the installed third-party dependency inventory. Neither `chromadb` nor `llama-index-vector-stores-chroma` appears in the 133-package report.

**Result:** PASS for the base artefact and fresh-install third-party dependency closure. No known vulnerability was reported. This result does not cover the universal lock or optional Chroma extra; those are recorded separately in task 1.6.
