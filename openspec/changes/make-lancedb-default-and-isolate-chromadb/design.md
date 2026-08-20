## Context

The repository already has a `VectorStore` ABC, lazy registry and ChromaDB and
LanceDB adapters. The current default appears in at least four executable
surfaces, not three: `config/__init__.py`, `config/defaults.yaml`,
`.env.example`, and `EffectiveSettings.vector_store` in
`core/settings.py`. The canonical `vectordb-abstraction` specification also
states that Chroma is the default.

`core/vectordb/__init__.py::get_default_store` currently contains a concrete
Chroma fallback. Replacing that with another constructor would still violate
the canonical composition-root rule: `compose.py` owns object construction and
core consumers receive injected dependencies. `core/retrieval/sparse.py` also
probes Chroma capability by import rather than asking the selected store.

Stage 5 evidence establishes useful adapter-level parity, but not complete
production qualification. Experiment 2 used synthetic precomputed vectors;
Experiment 3 was Chroma-only and used the old squared-L2 regime; Experiment 4
covered limited cache/generation behaviour; Experiment 6 used Chroma; TDR-013
records the narrowed-lock LanceDB ingestion block as untested.

ChromaDB remains affected by CVE-2026-45829 with no accepted patch. This
project's local `PersistentClient` and optional `CloudClient` do not start the
vulnerable server, but optionalisation does not automatically satisfy a policy
that scans the universal lock or all declared extras.

## Goals / Non-Goals

**Goals:**

- Qualify the existing LanceDB production lifecycle before promotion.
- Remove Chroma packages from the built base wheel and clean base environment.
- Establish one canonical LanceDB default without adding a second composition
  root.
- Keep optional backend and capability handling registry/store driven.
- Fail clearly before users accidentally abandon access to legacy Chroma data.
- Obtain an auditable release-policy disposition for residual lock/extra risk.
- Calibrate Stage 6 against the qualified final store baseline.

**Non-Goals:**

- No automatic Chroma-to-LanceDB migration.
- No deletion or rewriting of historical Chroma evidence or data.
- No claim that moving a vulnerable package to an extra makes the package safe.
- No neutral rename of `CHROMA_SCAN_PAGE_SIZE` in this change.

## Decisions

### D1: LanceDB qualification is a promotion pause gate

Before changing the executable default, run a TDR-014-admissible LanceDB
qualification at the final pre-flip commit and lock. It must cover real
document parse/chunk/embed/write, process restart/reopen, dense query, BM25
hybrid query, metadata filters, unchanged re-ingest, replacement, document and
collection deletion, identity stamping, generation invalidation, partial-write
recovery and the narrowed-lock path.

The qualification records requested/effective backend, URI/index identity,
score kind, embedding identity, lock hash, raw operation rows and atomic
completion. A failed, incomplete or not-evaluable gate blocks the default flip.
Synthetic adapter parity remains supporting evidence, not a substitute.

### D2: Chroma remains a supported but quarantined optional extra

Move `chromadb` and `llama-index-vector-stores-chroma` into
`[project.optional-dependencies].chroma`, retaining supported floors because
the project deliberately continues Chroma compatibility. The dependency-floor
test does not itself require keeping a deleted dependency; continued support is
the reason for the extra.

The base wheel must not declare either package as unconditional `Requires-Dist`.
A fresh installation of that wheel without extras must contain neither
distribution. `uv.lock` retains them because it locks all extras; it is not
manually edited.

### D3: One settings default and one composition root

All executable/default documentation surfaces change together, including
`EffectiveSettings.vector_store`. Tests assert agreement between the typed
resolver, YAML defaults, effective-settings model and environment example.

`compose.py` remains the only constructor. `get_default_store()` returns an
already installed process-wide store and raises a controlled `RuntimeError` if
composition has not installed one. It does not import settings, compose or a
concrete store and does not build a fallback.

This removes, rather than relocates, the second composition root. Callers and
tests that relied on lazy construction must compose or inject explicitly.

### D4: Registry-owned optional-backend metadata

Each lazy registry entry may declare required import modules/distributions,
optional-extra name and installation guidance. Registry resolution generically
distinguishes:

1. unknown backend;
2. required package(s) absent;
3. partial optional installation;
4. registered factory import failure/broken installation.

The dispatch path contains no `if vector_store == "chroma"` branch. Errors name
the selected backend and backend-specific guidance, retain the original cause
for broken installs and never expose credentials. Both Chroma packages are
checked independently.

The user guidance covers the supported source-tree command and packaged-extra
form rather than assuming every user runs `uv sync` in a checkout.

### D5: Capabilities belong to the selected store

Sparse/native capability is obtained from the selected store instance or its
registry metadata. Installing Chroma while selecting LanceDB cannot change
LanceDB's sparse route. LanceDB uses the existing BM25 path unless LanceDB
itself advertises another supported capability.

### D6: Explicit-selection provenance and fail-closed legacy handling

Settings resolution records whether `VECTOR_STORE` came from explicit user
input (constructor/CLI, environment or `.env`) or from shipped defaults. This
provenance is internal configuration data, not another backend selector.

If a recognised legacy Chroma layout is present and the backend was not
explicitly selected, startup fails before ingestion or retrieval. Recognition
requires Chroma markers such as `chroma.sqlite3` or the documented segment
layout; a merely non-empty unrecognised directory emits a warning instead.

The error names the untouched directory and requires one explicit choice:

- install the `chroma` extra and set `VECTOR_STORE=chroma`; or
- set `VECTOR_STORE=lancedb`, acknowledging that re-ingestion is required.

Explicit LanceDB selection is acknowledgement. The software never deletes,
moves or writes the legacy directory as part of this decision.

### D7: Validation ordering for Chroma settings

Backend/settings compatibility is validated before Chroma credential
completeness. `VECTOR_STORE=lancedb` plus `CHROMA_MODE=cloud` or any non-empty
trimmed `CHROMA_CLOUD_*` value always yields the backend-mismatch error, even if
the API key is absent. Credential values never appear in errors.

### D8: Base and extra tests are explicit, not skip-driven by accident

Chroma imports move inside Chroma-only fixtures/modules. Shared contract tests
retain their LanceDB cases in a Chroma-free environment; module-level
`importorskip` may not skip those cases. The base job has an exact allowed-skip
list and expected collected/executed counts. Every Chroma-skipped case is run
in the extra job.

The base tripwire proves both distributions are absent with import metadata and
installed-distribution inspection, then imports and exercises the default
runtime and proves no Chroma module loaded. Built-wheel metadata is inspected.
Base lint/import contracts must pass without installing Chroma; the lint job is
not permitted to hide a base import dependency by adding the extra.

### D9: Security release clearance is an external pause gate

ADR-049 records risk, but does not self-clear the release gate. The change
must produce:

- built-base-wheel dependency metadata;
- a fresh base-wheel installation inventory;
- a base-artifact/SBOM scan distinct from the universal-lock scan;
- a source/entry-point check that project production paths do not launch
  Chroma's Python FastAPI server;
- the residual universal-lock and extra scan result.

The release-policy owner must be named in the evidence and approve or reject a
dated exception with scope, rationale, expiry/review date and patch/advisory
triggers. Until that approval exists, the release remains blocked. If policy
cannot accept the residual universal-lock finding, the fallback is a separately
locked/distributed plugin or temporary removal of Chroma support.

### D10: Patch reconsideration requires converging authority

A future Chroma version permits a new reassessment only when all of the
following hold:

- it is an official maintainer PyPI release;
- a fixing commit or release note is linked;
- the project's named authoritative advisory source excludes the version;
- a renewed review, preferably with an isolated regression/PoC check, accepts it.

If authoritative sources disagree, quarantine continues. Reassessment requires
a separate OpenSpec and never automatically changes the default or base group.

### D11: Experiment policy applies by first measured run

Every experiment whose first admissible measured row occurs after ADR-049 uses
LanceDB unless store backend is a declared manipulated factor. This includes
already-created Stage 6 plans and runners. Before measurement, inventory
Experiments 10b, 12, 13 and 14 and any other pending calibration harness;
rebuild/port their immutable index to LanceDB or document a controlled store
factor and limitation.

Completed raw evidence remains immutable. Historical Stage 5 security notes
receive dated append-only addenda; their original verdicts are not rewritten.

### D12: Documentation and rollback are data-aware

The drift sweep covers executable defaults, `EffectiveSettings`, source
docstrings, README/guides, test documentation, changelog/release material,
ADR-003 status, ADR index and pending Stage 6 plans. Historical ADR-003 text is
not rewritten; ADR-049 marks it superseded for the default decision.

Rollback after LanceDB ingestion is: explicitly pin and verify
`VECTOR_STORE=lancedb`, then revert software. Reverting to a Chroma-default
version without the pin can make newly written LanceDB data appear missing.

## Risks / Trade-offs

- Fail-closed legacy handling is stricter than a warning, but it prevents a
  hidden desktop-client stderr stream from becoming an accidental data/cost
  decision.
- The full qualification and split CI matrix delay the default flip. That cost
  is preferable to calibrating or releasing against an unqualified default.
- A formal risk exception may be refused. Optionalisation improves base
  exposure but does not override the repository's security policy.

## Migration Plan

1. Run and accept the LanceDB qualification pause gate.
2. Move dependencies and establish clean-base/extra CI.
3. Remove lazy construction and add generic registry/capability metadata.
4. Add explicit-selection provenance and fail-closed legacy detection.
5. Flip all default/spec surfaces together.
6. Port or constrain pending Stage 6 experiments and freeze their LanceDB index.
7. Produce security artefacts and obtain release-policy disposition.
8. Write ADR-049, migration, rollback and supersession documentation.
9. Run Stage 6 calibration only on the qualified final baseline.

Rollback pins and verifies LanceDB before reverting software. No automatic data
surgery is performed in either direction.

## Open Questions

None may be deferred as “if required” implementation tasks. The security owner,
scanner outputs, expected test counts and lint environment are evidence fields
that must be resolved before the corresponding gate can pass.
