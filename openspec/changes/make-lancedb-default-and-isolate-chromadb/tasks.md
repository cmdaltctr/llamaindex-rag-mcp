## 0. LanceDB promotion qualification

- [x] 0.1 Freeze a TDR-014 plan at the final pre-flip commit and lock for real LanceDB lifecycle qualification; record requested/effective backend, URI/index identity, score kind, embedding identity, corpus/config identity and raw operation schema. (PASS — plan.json + protocol.md frozen; manifest at experiments/19-lancedb-lifecycle-qualification-2026-08-21/output/run2/manifest.json, commit a57abf3, lock 3a225230a6eb)
- [x] 0.2 Run real parse/chunk/embed/write, restart/reopen, dense retrieval, BM25 hybrid retrieval, metadata filters, unchanged re-ingest, replacement, document deletion, collection deletion, identity stamping, generation invalidation, interrupted-write recovery and the narrowed-lock ingestion path. (PASS 14/14 gates — output/run2/raw_rows.jsonl + verdicts.json; run1 FAIL lineage kept on disk)
- [x] 0.3 Commit raw rows, manifests, atomic checkpoints and a per-gate verdict. Any failed, incomplete or not-evaluable gate blocks tasks 2.1–2.3 and the public default flip. (PASS — results.md verdict table; gate-0 pause condition met; blocks lifted for 2.1–2.3)

## 1. Packaging and objective security evidence

- [ ] 1.1 Move `chromadb` and `llama-index-vector-stores-chroma` from base dependencies into `[project.optional-dependencies].chroma`, retaining supported floors because Chroma compatibility remains supported.
- [ ] 1.2 Regenerate `uv.lock`; do not edit optional Chroma entries out manually.
- [ ] 1.3 Build the base wheel and inspect metadata: neither Chroma package is an unconditional `Requires-Dist`; record the wheel hash and metadata output.
- [ ] 1.4 Install the base wheel in a fresh environment and prove both distributions absent using import metadata and installed-package inventory; run the base default path.
- [ ] 1.5 Generate and scan a base-wheel/base-install SBOM separately from the universal lock. Record scanner name/version, artefact identity and complete results.
- [ ] 1.6 Record the residual universal-lock/all-extras advisory result. Obtain a named policy-owner decision with date, scope, rationale, expiry/review date and patch/advisory triggers. Do not claim release clearance without approval.
- [ ] 1.7 If policy refuses the residual finding, stop this release path and open a separate decision to move Chroma into a separately locked/distributed plugin or remove support temporarily.

## 2. Canonical defaults and composition

- [ ] 2.1 After gate 0 passes, flip every executable default together: `config/__init__.py`, `config/defaults.yaml`, `.env.example` and `EffectiveSettings.vector_store`; add an agreement test across all four.
- [ ] 2.2 Remove construction from `get_default_store()`. It MUST return the installed instance or raise a controlled not-composed error and MUST NOT import settings, compose or concrete stores.
- [ ] 2.3 Update callers/fixtures that relied on lazy construction to compose or inject explicitly; preserve the process-wide single-instance guarantee after installation.
- [ ] 2.4 Add explicit backend-selection provenance for constructor/CLI, environment, `.env` and shipped defaults.
- [ ] 2.5 Add early Chroma/backend compatibility validation before credential completeness. Test backend × mode × absent/partial/complete/whitespace credential cases without exposing values.
- [ ] 2.6 Generalise effective-store runtime summaries to the selected backend and location.

## 3. Registry and selected-store capabilities

- [ ] 3.1 Extend lazy registry entries with required modules/distributions, extra name and backend-specific installation guidance; keep central dispatch free of store-name branches.
- [ ] 3.2 Distinguish unknown, absent, partial and factory-import-failed backends generically. Test `chromadb` and `llama-index-vector-stores-chroma` independently and preserve original causes for broken installs.
- [ ] 3.3 Resolve native/sparse capability from the selected store or registry entry. Test LanceDB with the Chroma extra absent and present; both MUST select the same LanceDB/BM25 route.
- [ ] 3.4 Test explicit Chroma without the complete extra fails startup and never silently opens LanceDB.

## 4. Fail-closed legacy-data decision

- [ ] 4.1 Define recognised Chroma markers (`chroma.sqlite3` and documented segment layout) separately from a merely non-empty directory.
- [ ] 4.2 Recognised legacy data plus default-derived backend MUST fail startup before ingestion/retrieval, name the untouched directory and require explicit Chroma keep-and-pin or explicit LanceDB re-ingestion acknowledgement.
- [ ] 4.3 Explicit LanceDB MUST acknowledge re-ingestion and leave legacy data untouched; explicit Chroma with the complete extra MUST preserve access. Unrecognised non-empty directories MAY warn.
- [ ] 4.4 Add an integration assertion that the migration diagnostic reaches the real CLI/MCP operator path, not only `caplog`.

## 5. Test collection and CI isolation

- [ ] 5.1 Remove module-level Chroma imports from shared `conftest.py` and shared contract modules; split or lazily import Chroma-only fixtures/cases so LanceDB parameters still collect without the extra.
- [ ] 5.2 Define exact Chroma markers/files, expected base collection count, executed count and allowed-skip list. Every skipped base case MUST be named and run in `chroma-extra` CI.
- [ ] 5.3 Make one deterministic autouse fixture install tmp-path LanceDB plus matching effective settings and reset both; do not depend on fixture-order accidents.
- [ ] 5.4 Add a clean-base tripwire covering built-wheel metadata, both distribution absences, default runtime/search and unloaded Chroma modules.
- [ ] 5.5 Run base tests, coverage, Ruff and all import-linter contracts without the extra. Base lint is mandatory and MUST NOT install Chroma to make the graph pass.
- [ ] 5.6 Add the Chroma-extra job with `uv sync --frozen --extra chroma`; run every Chroma contract, legacy, hybrid and cloud case plus the Chroma coverage slice.
- [ ] 5.7 Add the `chroma` group to lowest-direct/floor CI and retain exact expected cases.

## 6. Stage 6 baseline and experiment policy

- [ ] 6.1 Apply the policy to every experiment whose first admissible measured run follows ADR-049, regardless of when its directory was created.
- [ ] 6.2 Inventory pending Experiments 10b, 12, 13 and 14 and any other prepared calibration runner. Port/rebuild immutable inputs for LanceDB or declare backend as a manipulated factor with a limitation.
- [ ] 6.3 Add plan/runner/preflight assertions for effective LanceDB and immutable index identity before any Stage 6 measured row.
- [ ] 6.4 Do not calibrate on Chroma and later treat the result as LanceDB evidence. Freeze the qualified LanceDB index before Stage 6.

## 7. Documentation, ADR and patch trigger

- [ ] 7.1 Write ADR-049 with qualification evidence, four default surfaces, composition-root rule, registry metadata, legacy fail-closed decision, migration/rollback, security owner/exception and supersession of ADR-003 for the default.
- [ ] 7.2 Document the patch trigger: official PyPI release, linked fix, exclusion by the named authoritative advisory and renewed review/regression evidence; disagreement keeps quarantine.
- [ ] 7.3 Sweep active references in `.env.example`, README, CONTRIBUTING, AGENTS, changelog/release material, tests documentation, source docstrings, ADR index, ADR-003 status, guides and pending experiment plans. Use an executable search gate excluding immutable historical evidence.
- [ ] 7.4 Document source-checkout and packaged-extra Chroma installation, the active advisory, prohibition on exposing Chroma's Python FastAPI server, legacy choices and data-aware rollback (`VECTOR_STORE=lancedb` pin and verification before revert).
- [ ] 7.5 Add only dated append-only notes to completed Stage 5 security/experiment records; do not rewrite their original verdicts.

## 8. Final gates

- [ ] 8.1 In fresh environments, run base-wheel install plus the complete base suite, then `uv sync --frozen --extra chroma` plus the exact Chroma suite; record collected/executed/skipped counts.
- [ ] 8.2 Run `ruff check .`, `ruff format --check .`, base `lint-imports` with all existing contracts, dependency-floor tests and `openspec validate make-lancedb-default-and-isolate-chromadb --strict`.
- [ ] 8.3 Run the normative-default drift check across canonical specs and executable surfaces; zero current-tense Chroma-default contradictions are allowed outside excluded historical evidence.
- [ ] 8.4 Inspect the complete diff and prove no automatic legacy-data migration/deletion and no historical raw-evidence rewrite occurred.
- [ ] 8.5 Mark the release gate clear only if qualification, base artefact evidence and the named policy-owner decision all pass. Otherwise record the exact blocker and stop.
