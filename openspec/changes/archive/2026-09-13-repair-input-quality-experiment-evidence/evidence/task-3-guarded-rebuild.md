# Section 3 evidence: experiment 25 guarded rebuild (tasks 3.1–3.6)

> **SUPERSEDED IN PART (audit correction, 2026-09-09, later the same day):**
> a blocking security audit rejected the interim approval-gated path
> described below. See "Correction round" at the end of this file for the
> authoritative final state: unconditional rebuild refusal restored,
> scaffold split out as UNVERIFIED, tasks 3.4/3.6 unchecked, 3.5 partial.

Date: 2026-09-09. Worktree `feat/improve-rag-input-quality-5`. All commands
ran offline with `uv run --no-sync`; no package was installed, no embedding
request was sent, no paid work occurred.

## Task 3.1 — offline authorisation tests (DONE)

`tests/test_exp25_build_authorisation.py` (rewritten from the provisional
a-test draft): 28 offline tests with fake transports covering missing
approval/estimate, stale estimates (tampered digest, changed corpus, changed
`uv.lock`, changed `src/omrg` runtime source, tokenizer fallback, missing
pricing date, missing baseline comparison), approval digest/destination
mismatch, six protected-destination cases, `--force` bypass prevention,
approved build above 15%, marker identity reuse, failed-pack abort, and the
per-batch budget stop (unit and main level).

- Fail-before: `uv run --no-sync pytest tests/test_exp25_build_authorisation.py -q`
  scored **23 failed, 1 passed** against the pre-repair zero-argument gate.
- Pass-after: **28 passed** (33 passed with the two pre-existing exp25 test
  files; their 2 skips are the adapter-parity dependency block, below).
- Mutation checks (protection removed, then restored byte-identical —
  SHA-256 verified after each restore):
  - destination protection disabled → 6 tests fail
  - budget-stop comparison disabled → 2 tests fail
  - identity match disabled → 2 tests fail
  - pack-failure detection disabled → 1 test fails (file-detail check also
    independently catches the synthetic failure — defence in depth)
  - token-cap binding disabled → 1 test fails
  - runtime-source digest constant → 1 test fails

## Task 3.4 — estimate-bound approval gate (DONE)

`experiments/25-token-chunking-ablation-2026-09-08/build_index.py`:
`_preflight_cost_gate(estimate, approval, request_identity, destination, force)`
replaces the unconditional refusal. Every refusal prints an actionable reason
and exits 1 before any runtime import, so no embedding request can occur.
Approval binds: estimate digest (SHA-256 over canonical JSON minus `digest`),
live identity (corpus content, fixed settings, `build_index.py` hash,
`src/omrg` runtime-source tree digest, `uv.lock` hash, tokenizer
model+revision), a destination outside every protected root
(`EXP_DIR/output`, exp22/exp25 preserved stores; both-direction path
containment), a currency spending limit AND an independent
`max_request_tokens` cap (enforced ceiling = the lower of the two), and an
operator identity. The gate displays baseline/candidate request tokens,
percentage difference, approximate cost and the pricing date, and states
provider retries/billing can differ. The frozen 15% threshold is reported as
judging the measured result only; an approved build proceeds above it.
`BudgetStopEmbedder` wraps the injected embed model at the single production
choke point (`get_text_embedding_batch`, `core/ingestion/replacement.py`);
a pack reporting error statuses aborts exit 1 with no marker; markers are
reused only on matching run identity; the frozen historical
`output/build_done.json` is read-only. Retrospective `verify_accounting.py`
is untouched and remains separate. `--force` grants nothing.

## Task 3.5 — entry points and rebuild instructions (DONE)

- `overnight.sh` rewritten: no longer runs `token_accounting.py`; requires
  `estimate+approval+destination` arguments; `bash -n` clean.
- Repo sweep: the only entry point feeding the deprecated counter was
  `overnight.sh`; remaining `token_accounting` references are historical
  records (TDR-022/023, protocol, results artefact table).
- `experiments/25-.../results.md`: dated "Recovery clarification
  (2026-09-09): guarded rebuild path" section + artefact-table row updated;
  reproduction snippet no longer cites the removed `--resume` flag.
- Marker reuse checks run identity (3.4).
- Out of scope, flagged for task 5.1: `report.py:366` still prints
  `build_index.py --resume` (report-generator repair is blocked per 5.1).

## Task 3.6 — TDR-023 follow-up (DONE)

`docs/tdr/023-reconstructed-nodes-are-not-stored-nodes.md` gained a dated
"Follow-up (2026-09-09): repaired pre-spend path replaces the blanket
refusal" section (157 → 235 lines, additions only): what changed, estimates
vs billing distinction, test evidence with exact commands and mutation
results, the pending estimator/adapter install, accepted residual risks
(HOME-derived protected roots, TOCTOU windows, lock-wide advisories deferred
to the change-wide security reassessment), and the entry-point change.

## Tasks 3.2 and 3.3 — BLOCKED on the installed adapter

Dependency determination (first action of the session):

```
uv run --no-sync python -c "import importlib.util; \
  importlib.util.find_spec('llama_index.embeddings.openai_like')"
→ MISSING
```

`llama-index-embeddings-openai-like` is not installed. It is the production
adapter for exp25's embedding configuration (cloud/openrouter →
`OpenAILikeEmbedding`, see `src/omrg/core/providers/embeddings/openrouter.py`),
and both cloud providers route through it. Consequences, per the operator's
instruction not to bypass the installed-parity requirement and not to install:

- **3.2 BLOCKED**: the production-preparation dry run cannot construct the
  real embedder, and request-text parity against the installed adapter
  cannot be proven. The two existing parity tests
  (`test_installed_adapter_normalises_request_text`, sync+async) SKIP for
  this reason. No estimator script was written — unverifiable code would
  violate the fail-before/pass-after discipline.
- **3.3 BLOCKED**: identified baseline/candidate request-token estimates
  cannot be produced without the estimator. The gate's estimate schema,
  display and invalidation rules (fallback, missing comparison, missing
  pricing date) are implemented and tested with synthetic documents under
  3.1/3.4; producing real estimates remains blocked.

**Exact install requiring operator approval:** `uv sync --extra openrouter`
(adds `llama-index-embeddings-openai-like>=0.3.0` and
`llama-index-llms-openai-like>=0.5.0`, per `pyproject.toml`). The alternative
`--extra llamacpp` provides the same embeddings adapter. Installing would not
change defaults; the estimate/budget guards stay active.

## Delegation record

- a-test pre-empted: the operator explicitly assigned test expansion to this
  session (the provisional file came from the prior a-test run).
- a-tech-researcher: not called — no new dependency was imported or added.
- a-security: full audit returned findings; three in-scope defects were fixed
  (runtime-source identity, independent token cap, marker-after-failed-pack —
  the last reproduced before the fix) and re-verified with new regression
  tests and mutation checks. Lock-wide CVE reachability (chromadb, nltk)
  deferred to the change-wide security reassessment (section 8). Scanner
  noise (gitleaks on the public HF revision, bandit on a replaced assert)
  triaged as non-vulnerabilities.
- a-docs: wrote the TDR-023 follow-up; amended in place after the
  post-audit fixes.
- a-refactor: read-only review; both suggested cleanups (repeated refusal
  scaffold, non-blank helper) explicitly recommended deferral to a future
  edit for evidence stability. Deferred accordingly.

## Integrity verification (post-work)

- Mixed-patch files byte-identical to session start:
  `src/omrg/integrations/pdf/ocr_routing.py` and
  `tests/test_ocr_routing_gate.py` (SHA-256 re-checked; see tasks.md 1.1).
- All 21 frozen inventory files re-hashed byte-identical (experiment 25–28
  plans, raw results, markers, accounting outputs).
- `.env` never read or written (dotenv neutralised in every test loader).
- Preserved indexes untouched; no destination directories created.

## Correction round (2026-09-09, audit-mandated): refusal restored

The operator's blocking audit findings and their dispositions:

1. **Crafted estimate self-digest passes without production preparation**
   — CONFIRMED and fixed. The gate validated only internal consistency;
   a handcrafted document pair satisfied every check. Regression added
   FIRST (`test_handcrafted_estimate_with_valid_approval_still_refuses`)
   and proven failing against the interim code (fail-before: 1 failed —
   the build proceeded); then `build_index.main` was changed to refuse
   every rebuild unconditionally BEFORE estimate/approval files are read
   and before runtime setup is imported (pass-after). The regression test
   proves its documents satisfy the scaffold gate by calling
   `_preflight_cost_gate` directly, then requires main to exit 1 with
   zero runtime/embedding requests.
2. **Missing estimator/installed-adapter parity (3.2/3.3)** — the
   approval path cannot be verified end-to-end; it is no longer live.
   All gate logic moved to `estimate_gate.py`, banner-marked UNVERIFIED
   SCAFFOLD, never called by `build_index.main`.
3. **File sizes** — split (counts verified by the independent read-only
   refactor audit): `build_index.py` 90 lines, `estimate_gate.py` 438,
   `tests/test_exp25_build_authorisation.py` 251,
   `tests/test_exp25_estimate_gate_scaffold.py` 382 (all < 500;
   ruff check + format clean). One deliberate duplication (`EXP_DIR`
   defined in both modules) is the price of keeping the scaffold
   unreachable from the live builder.
4. **TDR "accepted" residual risks without operator permission** —
   removed; risk items listed as UNRESOLVED pending operator decision.
   TDR follow-up rewritten: refusal restored, scaffold unverified.
5. **Task states** — 3.4 and 3.6 unchecked; 3.5 marked PARTIAL (entry
   points proven; marker-identity half unprovable on a refusing build
   path; historical marker reuse allowed as instructed); 3.1 evidence
   updated to include the correction-round regression.
6. **Entry points** — `overnight.sh` exits 1 with the blocked status;
   `results.md` recovery clarification rewritten (rebuilds blocked until
   estimator verified).

### Live behaviour after correction

- `build_index.py` (no args): historical marker present → clean skip,
  zero requests (allowed reuse).
- `build_index.py --force` (with or without estimate/approval/destination
  documents, including documents the scaffold would accept): exit 1,
  message names the missing estimator and parity verification, zero
  runtime/embedding requests, no marker written, documents never read.
- Combined scoped tests: 32 passed, 2 skipped (adapter-parity block).

### Exact unresolved conditions (nothing accepted by the operator)

- Offline estimator absent; adapter install (`uv sync --extra openrouter`)
  awaits operator approval. No estimate document is legitimate.
- Request-text parity vs the installed adapter (3.2) unverified; two
  parity tests skip.
- Marker-identity reuse unproven on any live path (scaffold only).
- `report.py:366` still prints the removed `--resume` flag (task 5.1).
- Unresolved risks (operator decision pending): `Path.home()`-derived
  protected roots; corpus/destination TOCTOU windows; lock-wide
  dependency advisories (section 8 reassessment).
- Test-hardening note from the independent confirmation audit: the
  handcrafted-estimate regression currently proves zero runtime/embedding
  requests via import traps; explicit file-read traps would strengthen it
  against a future implementation that reads documents then refuses.
  Recorded for the future estimator work; no current bypass exists.

### Independent confirmation (2026-09-09)

Read-only a-security confirmation returned **REFUSAL CONFIRMED**: no
reachable build, approval-gate, runtime-import or embedding path exists;
the only exit-zero route is the read-only historical-marker skip (marker
mtime/hash unchanged across an independent skip run); an additional
runtime trap exercised eight argument combinations (including all
documents plus `--force`) — all exit 1 with zero document reads and zero
omrg imports. The read-only refactor verification confirmed the split
(7/7 checks: line counts, no dead code, standalone purity, no
build_index→estimate_gate import, import-trap mechanics, no coverage
masking, ruff clean).
