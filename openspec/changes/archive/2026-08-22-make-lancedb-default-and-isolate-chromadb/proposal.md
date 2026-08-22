## Why

ChromaDB 1.5.9 is a critical direct dependency affected by CVE-2026-45829,
with no accepted patched release as of this proposal. The project does not
start Chroma's Python FastAPI server, but the base release remains policy
blocked while the vulnerable package is an unconditional direct dependency.

LanceDB already implements the shared vector-store contract, but existing
Stage 5 evidence does not qualify every production ingestion/reopen/mutation
path. The default may change only after a TDR-014-admissible LanceDB lifecycle
qualification closes that evidence gap and the residual optional-dependency
finding receives explicit release-policy disposition.

## What Changes

- **BREAKING**: after qualification, change the default `VECTOR_STORE` from
  `chroma` to `lancedb` in every normative settings and specification surface.
- Move `chromadb` and `llama-index-vector-stores-chroma` from base dependencies
  into a named `chroma` optional extra.
- Keep `compose.py` as the sole construction root. The process-wide accessor
  returns only an injected store and fails clearly if composition has not run;
  it does not construct a fallback store.
- Give lazy registry entries backend-specific availability metadata so missing,
  partial and broken optional installations produce generic actionable errors
  without store-name branches in dispatch.
- Resolve sparse/native capabilities from the selected store rather than from
  whichever optional packages happen to be installed.
- Reject Chroma mode/credential settings with a non-Chroma selected backend
  before validating Chroma credential completeness.
- Fail closed when recognised legacy `./chroma_db/` data exists and no explicit
  backend choice was made. Require the operator to choose keep-and-pin Chroma
  or acknowledged LanceDB re-ingestion; never modify the old directory.
- Prove the base wheel and fresh base environment contain no Chroma packages,
  scan the base artefact separately, and require a named, dated disposition for
  the residual universal-lock/extra finding before the release gate is cleared.
- Add base-install and Chroma-extra CI jobs with explicit collection and skip
  expectations; preserve shared LanceDB coverage when Chroma is absent.
- Apply the LanceDB experiment policy to every experiment whose first
  admissible measured run occurs after ADR-049, including already-prepared
  Stage 6 harnesses.
- Write ADR-049 with qualification evidence, migration/rollback, security
  ownership, exception expiry and a strict patched-release reconsideration
  trigger.

## Capabilities

### New Capabilities

- `experiment-vector-store-policy`: Defines the effective-store requirement
  for every not-yet-measured experiment after ADR-049.

### Modified Capabilities

- `vectordb-abstraction`: Changes the canonical configured default from Chroma
  to LanceDB while preserving registry dispatch and dependency injection.
- `lancedb-vector-store`: Makes qualified embedded LanceDB the base-install
  default and fails closed for unacknowledged recognised legacy Chroma data.
- `vector-store-registry`: Adds generic optional-backend availability metadata,
  selected-store capabilities and an injected-only process accessor.
- `chroma-cloud-backend`: Makes Chroma modes conditional on explicit backend
  selection and the optional extra and strengthens the quarantine trigger.
- `dependency-floor-integrity`: Separates base and extra contracts and makes
  residual security acceptance an explicit release gate.
- `config-composition-root`: Changes all resolved defaults, preserves
  `compose.py` as the sole constructor and records explicit-selection provenance.

## Impact

- Affects dependency metadata, `uv.lock`, four settings/default surfaces,
  composition/accessor behaviour, registry metadata, capability resolution,
  test fixtures, CI, experiment preparation, ADRs and user documentation.
- Existing Chroma data is never migrated or deleted automatically. Users must
  explicitly select Chroma with the extra or explicitly select LanceDB and
  re-ingest.
- `uv.lock` will continue to contain optional Chroma packages. This change
  clears the release gate only if the named security-policy owner accepts the
  base-artefact evidence and residual finding; otherwise Chroma must move to a
  separately locked/distributed plugin or be removed temporarily.
- Historical experiment evidence remains immutable.
