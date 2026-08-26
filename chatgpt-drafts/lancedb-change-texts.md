# LanceDB default and ChromaDB isolation — final text drafts

## 1. `VECTOR_STORE=chroma` without the optional extra

Raise `ValueError` with this text:

```text
Vector store 'chroma' is unavailable because the optional Chroma packages are not installed. Install them with `uv sync --extra chroma`, or remove `VECTOR_STORE=chroma` to use the default LanceDB backend. No fallback was performed.
```

## 2. Absent-extra and broken-install distinction

When neither optional Chroma package is importable, raise `ValueError` with:

```text
Vector store 'chroma' is unavailable because the optional Chroma packages are not installed. Install them with `uv sync --extra chroma`, or remove `VECTOR_STORE=chroma` to use the default LanceDB backend. No fallback was performed.
```

When one optional package is present but the other is absent, raise `ImportError`
from the original import exception. `{missing_packages}` is the comma-separated
set established by the independent package probes and must not contain
configuration values:

```text
Vector store 'chroma' was selected, but its optional installation is incomplete or broken. Missing package(s): {missing_packages}. Reinstall it with `uv sync --extra chroma` and inspect the chained exception for the original import failure. No fallback to LanceDB was performed.
```

If both package probes succeed but import or construction fails, raise
`ImportError` from the original factory exception with:

```text
Vector store 'chroma' was selected and its optional packages were found, but the backend could not be constructed. Reinstall it with `uv sync --extra chroma` and inspect the chained exception for the original failure. No fallback to LanceDB was performed.
```

## 3. Chroma cloud settings with LanceDB selected

```text
Chroma-specific settings (`CHROMA_MODE=cloud` or `CHROMA_CLOUD_*`) require `VECTOR_STORE=chroma`; the effective vector store is `lancedb`. Remove the Chroma-specific settings or select Chroma explicitly. Credential values were not included in this error.
```

## 4. Recognised legacy ChromaDB data without an explicit store choice

```text
Recognised ChromaDB data was found at `./chroma_db/`, but `VECTOR_STORE` was not explicitly selected. Startup has stopped to prevent an implicit switch to an empty LanceDB store. Choose one operator action: (1) install the optional backend with `uv sync --extra chroma` and set `VECTOR_STORE=chroma` to keep using the existing data; or (2) set `VECTOR_STORE=lancedb`, acknowledging that source-document re-ingestion into LanceDB is required. The `./chroma_db/` directory was not modified, migrated, or deleted.
```

## 5. Unrecognised non-empty legacy directory

```text
The directory `./chroma_db/` is non-empty but does not contain a recognised ChromaDB layout. Startup will continue with the default LanceDB backend. The directory will not be modified. Verify its contents before deleting or reusing it.
```

## 6. `.env.example` vector-store block

```dotenv
# ── Vector store ───────────────────────────────────────────────────────────────
# Backend selection: "lancedb" (the default) or "chroma".
# Chroma is optional; run `uv sync --extra chroma` before selecting it.
# Changing stores does not migrate existing vectors. Re-ingest source documents.
VECTOR_STORE=lancedb

# Shared collection/table name.
COLLECTION_NAME=documents

# LanceDB local data directory.
LANCEDB_URI=./lancedb

# Chroma-only local settings. Cloud mode or non-empty cloud credentials with a
# non-Chroma store are rejected rather than ignored.
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_MODE=local

# Chroma Cloud credentials (VECTOR_STORE=chroma and CHROMA_MODE=cloud only).
# Keep the key in .env only; credential values are never included in errors.
#CHROMA_CLOUD_API_KEY=
#CHROMA_CLOUD_TENANT=
#CHROMA_CLOUD_DATABASE=
```

## 7. `config/defaults.yaml` vector-store block

```yaml
# Vector store backend: "lancedb" (the default) or "chroma".
# Chroma requires the optional dependency group: uv sync --extra chroma
# Changing stores does not migrate existing vectors; re-ingest source documents.
VECTOR_STORE: lancedb

# Shared collection/table name.
COLLECTION_NAME: documents

# LanceDB local data directory.
LANCEDB_URI: ./lancedb

# Chroma local settings. Cloud mode or non-empty cloud credentials with a
# non-Chroma store are rejected rather than ignored.
CHROMA_PERSIST_DIR: ./chroma_db
CHROMA_SCAN_PAGE_SIZE: 10000
CHROMA_MODE: local
```

## 8. README migration section for existing Chroma users

```markdown
### Migrating an existing Chroma installation

LanceDB is the default vector store for new and unconfigured installations.
Chroma remains available as an optional backend and is never selected implicitly.

To continue using an existing `./chroma_db/` directory:

1. Install the optional packages with `uv sync --extra chroma`.
2. Set `VECTOR_STORE=chroma` explicitly.
3. Keep `CHROMA_PERSIST_DIR` pointed at the existing directory.

To move to LanceDB, set `VECTOR_STORE=lancedb` and re-ingest the source documents.
Vectors are not copied between backends automatically; retain the Chroma directory
until the LanceDB ingestion and retrieval checks have completed successfully.

If recognised Chroma data exists and no store is selected, startup fails closed and
prints both choices. The legacy directory is never modified, migrated, or deleted.
An unrecognised non-empty `./chroma_db/` produces a warning and is also left untouched.
```

## 9. ADR-049 skeleton

```markdown
# ADR-049: LanceDB as the Qualified Default Vector Store

**Date:** TODO-LOCAL  
**Status:** Proposed  
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ChromaDB is currently a direct base dependency and the default vector store. The
locked release is affected by CVE-2026-45829, for which no patched upstream release
is available at the time of this decision. The project does not start ChromaDB's
Python FastAPI server: local operation uses the embedded persistent client, cloud
operation uses an HTTP client, and the adapters pass precomputed embeddings.

The absence of the vulnerable server path lowers this project's exposure but does
not remove the supply-chain and release-policy cost of a critical vulnerable direct
dependency in every base installation. LanceDB already implements the project-owned
vector-store abstraction and is the intended base-install alternative. Its selection
as the default is conditional on completing the recorded qualification gates.

Changing a default also creates a migration hazard. An existing `./chroma_db/` can
otherwise be silently ignored while the application opens an empty LanceDB store.

## Decision

After the qualification gates below pass, make LanceDB the default vector store and
move `chromadb` and `llama-index-vector-stores-chroma` to the optional `chroma` extra.
Selecting Chroma without a complete extra must fail with an actionable error and no
fallback. Preserve the original import or factory exception as the chained cause.

Future experiments use LanceDB unless the vector store is a manipulated factor.
Committed experiment plans must still state the requested and effective store and
must satisfy the experiment-validity framework.

Legacy handling is fail-closed. When recognised `./chroma_db/` data exists and no
explicit vector-store choice was supplied, startup stops and presents two choices:
install the extra and select Chroma, or acknowledge LanceDB and re-ingest. No legacy
directory is modified automatically. An unrecognised non-empty directory produces a
warning and is left untouched.

## Evidence

- Qualification commit and lock identity: TODO-LOCAL.
- LanceDB ingestion and retrieval qualification result: TODO-LOCAL.
- Cross-store behavioural and metadata-parity gate result: TODO-LOCAL.
- Default-path base-install test result and test count: TODO-LOCAL.
- Chroma-extra test result and test count: TODO-LOCAL.
- Base-environment installed-distribution inventory: TODO-LOCAL.
- Base-environment SBOM and vulnerability-scan result: TODO-LOCAL.
- Universal lockfile scan result and recorded policy disposition: TODO-LOCAL.
- Strict OpenSpec validation result: TODO-LOCAL.

No qualification placeholder is evidence. This ADR remains Proposed until the
TODO-LOCAL entries are replaced by committed, reproducible results.

## Consequences

### Positive

- The default runtime path and base installed environment exclude ChromaDB.
- New installations use the qualified LanceDB adapter without extra selection.
- Chroma remains available for operators who explicitly install and select it.
- Recognised legacy data cannot be silently bypassed by the default change.
- Backend-specific import failures remain diagnosable through chained exceptions.

### Negative

- The change is breaking for users who relied on the implicit Chroma default.
- Existing Chroma vectors require explicit pinning or source-document re-ingestion.
- The universal `uv.lock` still resolves optional groups, so advisory scanners may
  continue to report CVE-2026-45829 until a patched release exists or policy changes.
- CI must verify both a Chroma-free base installation and the optional Chroma group.

### Neutral

- The vector-store abstraction and lazy registry remain the composition boundary.
- No automatic cross-backend vector migration is introduced.
- Chroma cloud credentials are valid only when Chroma is explicitly selected.

## Alternatives considered

| Alternative | Reason not chosen |
|---|---|
| Retain Chroma as a base dependency and default | Keeps the critical vulnerable direct dependency in every base installation and leaves the release-policy block unresolved. |
| Remove Chroma support entirely | Prevents existing embedded and cloud users from making an explicit, informed choice while no compatible migration is automatic. |
| Switch silently when legacy data is present | Can present an empty store as the active database and conceal the operator's existing vectors. |
| Auto-migrate the legacy directory | Backend representations are not interchangeable; safe migration requires source-document re-ingestion and verification. |
| Maintain separate lockfiles for base and extras | Adds lock-drift and release complexity; the selected policy instead distinguishes the base installed environment from the universal lock and records the residual advisory. |

## References

- CVE-2026-45829 / GHSA-f4j7-r4q5-qw2c.
- ADR-047: Semantic Vector Store Swappability.
- TDR-013.
- TDR-014: Experiment Validity Framework.
- OpenSpec change: `make-lancedb-default-and-isolate-chromadb`.
- Qualification evidence paths: TODO-LOCAL.
```

## 10. Task 3.2 test-matrix enumeration

```text
File: tests/test_vectordb_registry.py

| Test name | Spec scenario verified |
|---|---|
| test_unknown_name_raises_key_error_listing_registered_stores | vectordb-abstraction — Unknown store value; vector-store-registry — unknown-name classification remains distinct from dependency failure. |
| test_chroma_registry_reports_absent_extra_when_both_packages_missing | vector-store-registry — Optional backend is absent; chroma-cloud-backend — Chroma backend is installed as an incomplete or absent extra. |
| test_chroma_registry_reports_partial_install_when_chromadb_missing | vector-store-registry — Optional backend is partially installed, probing `chromadb` independently. |
| test_chroma_registry_reports_partial_install_when_llamaindex_adapter_missing | vector-store-registry — Optional backend is partially installed, probing `llama-index-vector-stores-chroma` independently. |
| test_chroma_registry_preserves_import_error_as_chained_cause | vector-store-registry — Backend import is broken after dependency probes succeed; original exception is preserved. |
| test_chroma_registry_preserves_factory_error_as_chained_cause | vector-store-registry — Backend factory construction fails; original exception is preserved and no fallback occurs. |
| test_chroma_absent_error_names_extra_command_and_lancedb_default | vector-store-registry — Optional backend is absent; config-composition-root — LanceDB is the default and the remediation names `uv sync --extra chroma`. |
```
