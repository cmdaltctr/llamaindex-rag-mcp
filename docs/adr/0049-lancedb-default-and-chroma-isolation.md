# ADR-049: LanceDB Default and Chroma Isolation

**Date:** 2026-08-21
**Status:** Accepted (release clearance granted 2026-08-22 under the signed policy-owner disposition — see Security Ownership and Release Gate)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Supersedes:** ADR-003 for the configured vector-store default only

## Context

ChromaDB 1.5.9 is affected by CVE-2026-45829 (PYSEC-2026-311). No accepted
patched release exists for this advisory at this decision date. The project does not launch
Chroma's Python FastAPI server. Chroma remains a supported compatibility path,
but it cannot remain an unconditional base dependency or the implicit choice.

LanceDB implements the existing `VectorStore` contract. Promotion required
production-lifecycle evidence rather than adapter parity alone. It also required
a safe response when a default-derived configuration meets recognised legacy
Chroma data.

## Decision

1. **Use embedded LanceDB as the canonical base-install default.** The four
   executable default surfaces are `config/__init__.py`,
   `config/defaults.yaml`, `.env.example`, and
   `core/settings.py::EffectiveSettings.vector_store`. Each resolves to
   `lancedb`.

2. **Keep Chroma as an explicit optional extra.** Install it in a source
   checkout with `uv sync --extra chroma`, or from a package with
   `pip install "rag-mcp[chroma]"`. Chroma packages do not belong to the
   base dependency set. Optionalisation does not clear CVE-2026-45829.

3. **Keep construction in the composition root.** `compose.py` resolves
   settings, verifies the selected registry entry, constructs the store, and
   installs it. `get_default_store()` returns only that injected instance. It
   raises a controlled error before composition and never constructs a fallback.

4. **Keep registry availability metadata.** Lazy registry entries declare
   required modules and distributions, the optional-extra name, and
   installation guidance. Generic resolution distinguishes unknown, missing,
   partial, and broken installations without backend-name branches in dispatch.

5. **Fail closed for recognised legacy Chroma data.** When `chroma.sqlite3`
   or the recognised segment layout exists and `VECTOR_STORE` came from a
   shipped default, startup stops before ingestion or retrieval. The operator
   must explicitly keep and pin Chroma, or explicitly select LanceDB and
   re-ingest. The old directory remains untouched.

6. **Record selection provenance.** Settings retain whether the backend came
   from explicit input or shipped defaults. This provenance controls the
   legacy-data guard; it is not another backend selector.

## Qualification Evidence

Experiment 19 qualified the LanceDB production lifecycle before the default
flip. Run 2 passed 14/14 gates at commit `a57abf372db521f201788662591da14c4dceabe0`
with lock hash `3a225230a6eb…`, embedded LanceDB, and
`nomic-embed-text` embeddings.

The gates covered real writes, restart and reopen, dense and BM25-hybrid
retrieval, metadata filters, unchanged re-ingest, replacement, document and
collection deletion, identity stamping, generation invalidation,
interrupted-write recovery, narrowed-lock concurrent reads, and manifest-plan
agreement.

Run 1 failed 12 of 14 gates because of harness defects. Its failure lineage is
retained with the raw evidence. Commit `a57abf3` corrected the harness without
changing production code. Run 2 is the qualifying result. The plan, protocol,
manifest, append-only raw rows, verdicts, and result table are retained in
`experiments/19-lancedb-lifecycle-qualification-2026-08-21/`.

## Migration and Rollback

1. For existing Chroma data, choose one path before startup:
   - Keep access: install the `chroma` extra, set `VECTOR_STORE=chroma`, and
     retain `CHROMA_PERSIST_DIR`.
   - Move to LanceDB: set `VECTOR_STORE=lancedb` and re-ingest source files.
2. Switching stores always requires re-ingestion. There is no automatic
   cross-backend migration, deletion, move, or rewrite of the legacy directory.

3. Before reverting software after LanceDB ingestion, set and verify
   `VECTOR_STORE=lancedb`. Keep that pin while reverting. A previous release
   can otherwise select Chroma and make the LanceDB data appear missing.

## Security Ownership and Release Gate

| Field | Required disposition |
| --- | --- |
| Owner | **Dr Muhammad Aizat Bin Md Hawari (named 2026-08-22)** |
| Record date | 2026-08-21 |
| Decision date | **2026-08-22 (APPROVE with quarantine)** |
| Scope | CVE-2026-45829 (PYSEC-2026-311) in the universal lock and `chroma` extra; the base wheel and fresh base installation are separate evidence. |
| Rationale | The base path uses LanceDB. The optional extra can remain visible to universal-lock or all-extra scans. Exposure is opt-in only: the vulnerable package never enters a base install and the project never starts Chroma's FastAPI server. |
| Expiry or review date | **2026-11-22 (90 days), or earlier on the first D10 trigger** |
| Release state | Cleared 2026-08-22 under the signed disposition in `openspec/changes/archive/2026-08-22-make-lancedb-default-and-isolate-chromadb/evidence/04-residual-lock-finding.md` |

The owner must record the scanner evidence, scope, rationale, expiry or review
date, and the triggers below. ADR-049 does not clear the release gate.

Chroma's Python FastAPI server must never be exposed by this project. The
supported local and cloud clients do not authorise running or publishing that
server.

## Patch-Reconsideration Trigger

Reconsider Chroma's quarantine only when all conditions below are met:

1. The version is an official maintainer release on PyPI.
2. A fixing commit or release note is linked to that release.
3. The named authoritative advisory source excludes that version.
4. A renewed review accepts the evidence, preferably with an isolated
   regression or proof-of-concept check.

If authoritative sources disagree, quarantine continues. A passing review does
not change the default or restore Chroma to the base dependency set. It requires
a separate OpenSpec change and a new decision review.

## Consequences

### Positive

- New base installations use the qualified embedded LanceDB implementation.
- Missing optional packages produce guidance from the selected registry entry.
- Recognised legacy Chroma data cannot be silently bypassed.
- The composition-root boundary has one store-construction path.

### Negative

- Existing Chroma users must make an explicit selection and install an extra.
- A backend change requires source-file re-ingestion into a fresh store.
- A universal-lock or all-extra scan can still report the active Chroma advisory.
- Release clearance was granted on 2026-08-22 under the signed disposition
  (owner Dr Muhammad Aizat Bin Md Hawari, APPROVE with quarantine, expiry
  2026-11-22 or earlier on the first D10 trigger). A universal-lock or
  all-extra scan can still report the advisory until a patched release;

### Neutral

- Chroma local and cloud modes remain supported after explicit selection.
- `CHROMA_SCAN_PAGE_SIZE` remains the shared paged-scan setting.
- Historical Chroma evidence and directories remain intact.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Keep Chroma as the base default | It retains a vulnerable direct dependency on the default release path. |
| Remove Chroma support | Existing local and cloud users need an explicit compatibility route. |
| Construct a LanceDB fallback in `get_default_store()` | It creates a second composition root and hides missing composition. |
| Warn for recognised legacy data | An operator can mistakenly open an empty LanceDB store and assume old data was migrated. |

## References

- OpenSpec: `openspec/changes/make-lancedb-default-and-isolate-chromadb/`
- Qualification: `experiments/19-lancedb-lifecycle-qualification-2026-08-21/`
  (`plan.json`, `protocol.md`, `output/run2/manifest.json`,
  `output/run2/raw_rows.jsonl`, `output/run2/verdicts.json`, `results.md`)
- Configuration: `.env.example`, `src/rag_mcp/config/defaults.yaml`,
  `src/rag_mcp/config/__init__.py`, `src/rag_mcp/core/settings.py`
- Runtime: `src/rag_mcp/compose.py`,
  `src/rag_mcp/core/vectordb/{__init__,registry,legacy,summary}.py`
- Related decisions: ADR-003, ADR-031, ADR-034, ADR-042, ADR-046
- Implementation commits: `e5af622`, `869105b`, `2deeaee`, `86b0e7a`,
  `554d463`
