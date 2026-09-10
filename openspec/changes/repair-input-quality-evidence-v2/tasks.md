# Tasks: repair-input-quality-evidence-v2

This is a planning change. All implementation checkboxes are intentionally
unchecked. The local agent owns implementation, experiment execution and
runtime validation. ChatGPT has performed static GitHub inspection only.

Use the existing environment. All local Python commands use
`uv run --no-sync`. Do not synchronise away experiment extras, install
dependencies or invoke paid providers. Commands are in `validation.md`.
Do not run original reproduction commands that overwrite evidence or call
providers. Preserve ADR-063/064 and original plans throughout.

## 1. Experiment 25 close-out

- [ ] 1.1 Pull the planning commit safely on the named branch. Read current
      AGENTS.md and every artefact in this change. Run change-scoped strict
      OpenSpec validation before implementation.
- [ ] 1.2 Record the starting commit, lockfile hash and protected historical
      SHA-256 inventory using validation section A. Preserve all Experiment 25
      files, original input-quality plans, ADR-063/064 and historical evidence
      for Experiments 26–28. Do not inventory personal PDFs.
- [ ] 1.3 Record a read-only local inventory of the preserved Experiment 22/25
      indexes using their existing data-location records. Keep paths private.
      Do not open them through a write-capable experiment runner.
- [ ] 1.4 Add `close-out.md` inside this change directory: operator declined
      Experiment 25 rerun on 2026-09-10; historical COMPLETE PASS and ADR-063
      remain; the existing unconditional build refusal remains. State no
      estimator, compatibility work, live builder or paid-run machinery follows.
- [ ] 1.5 Compare the Experiment 25 source and evidence hashes with the starting
      inventory. Confirm its entire pre-existing directory is unchanged.
      Do not execute its builder, evaluator or accounting tools. Close this
      stage before starting Experiment 26.

## 2. Experiment 26 repair and verification

- [ ] 2.1 Inspect Experiment 26 recovery candidates under the operator-supplied
      recovery directory. Compare each against the base and current tree.
      Record private source locations, SHA-256 values, public opaque origins,
      proposed destinations and selection rationale. Do not extract wholesale.
- [ ] 2.2 Select only Experiment 26 candidates that address this specification.
      Keep recovered evidence in separate amendment inputs. Do not restore
      historical output over committed files. Record missing or unverified
      candidates explicitly; do not recreate their contents.
- [ ] 2.3 Add `tests/test_exp26_evidence_validity.py`. Establish fail-before
      proof for equal incomplete arms, duplicate/mismatched IDs, inconsistent
      done/rows, category mismatch, invalid latencies, missing provenance,
      output overwrite and premature gate rounding. Exercise old behaviour;
      a missing new API or flag alone is not proof.
- [ ] 2.4 Repair Experiment 26's summariser with small pure evidence checks,
      using an experiment-local `evidence.py` if needed. Require both complete
      arms, exact ground-truth IDs and categories, well-formed rankings,
      finite latencies and required frozen gates. Do not change metric
      definitions or query preparation.
- [ ] 2.5 Assess historical runtime provenance against TDR-014. Link recovered
      facts only to the run they actually evidence. Represent missing facts
      explicitly; never generate a historical manifest from current settings.
- [ ] 2.6 Add the explicit amendment inputs and separate output contract in
      design D5 and validation B. Compare unrounded values. Invalid/incomplete
      evidence gets null verdict, reasons and non-zero exit. Refuse historical
      output aliases and existing amendment destinations.
- [ ] 2.7 Re-run the same regressions and record pass-after proof. Include a
      complete synthetic supported case, a valid empty ranking, and precision
      boundary cases. Block network/model/index access inside tests.
- [ ] 2.8 Run scoped Ruff and targeted pytest from validation C. Record exact
      commands, code identities, test outcomes and fail-before/pass-after logs.
- [ ] 2.9 Build the Experiment 26 evidence manifest from verified local inputs.
      Run the repaired offline summariser into
      `amendments/repair-input-quality-evidence-v2/experiment-26/`.
      Produce separate assessment, provenance and amended report. Mark
      unresolved historical execution explicitly; do not append old discussion.
- [ ] 2.10 In the amended report, qualify unsupported determinism, causal and
      execution claims. Retain the historical negative result as history.
      Do not claim a rerun or change the instruction/defaults.
- [ ] 2.11 Recheck historical input hashes and preserved index inventory.
      Record any unresolved recovery/provenance issue. Finish Experiment 26
      verification before starting Experiment 27.

## 3. Experiment 27 repair and verification

- [ ] 3.1 Inspect and compare Experiment 27 recovery candidates individually.
      Record source/destination hashes and selection rationale. Select only
      relevant verified code/tests; preserve original evidence and archives.
- [ ] 3.2 Add `tests/test_exp27_evidence_validity.py`. Prove fail-before for
      incomplete reference cells, equal incomplete measured arms, duplicate
      IDs, mismatched completion metadata, missing provenance, arbitrary
      Experiment 25 drift-cell fallback, output overwrite and pre-rounded
      gate decisions. Use baseline-compatible behavioural reproducers.
- [ ] 3.3 Repair the Experiment 27 summariser and a small local `evidence.py`
      helper if needed. Validate all four named cells and expected query
      membership. Keep reference and historical measured roles explicit.
      Do not substitute Experiment 26's raw arm for Experiment 22's baseline.
- [ ] 3.4 Apply full-precision frozen gates to admissible evidence only.
      Carry missing or incompatible reference provenance into the assessment.
      Keep interaction diagnostic and use the exact named Experiment 25
      reference for drift. Missing optional drift evidence stays unavailable.
- [ ] 3.5 Implement separate amendment outputs matching validation B.
      Label original measurement dates separately from recomputation.
      Keep token-cost diagnostics offline and optional; no model download.
      Do not present offline counts as historical billing or request totals.
- [ ] 3.6 Re-run unchanged assertions for pass-after proof. Test complete
      supported synthetic inputs, each invalid reference case, precision
      boundaries and unavailable optional tokenisation without network access.
- [ ] 3.7 Run scoped Ruff and targeted pytest from validation D. Record code
      identities and the fail-before/pass-after evidence.
- [ ] 3.8 Prepare the verified Experiment 27 evidence manifest. Recompute only
      existing inputs into
      `amendments/repair-input-quality-evidence-v2/experiment-27/`.
      Write the separate assessment, provenance and report. Preserve original
      results, discussions and checkpoints.
- [ ] 3.9 Qualify unsupported execution, billing and causal claims in the
      amendment. State the cross-date/index limitations and that FreshStack
      did not exercise OCR. Preserve the historical negative result and
      Experiment 25 promotion; do not edit either ADR.
- [ ] 3.10 Recheck historical hashes and index inventories. Record remaining
      provenance gaps. Complete this stage before starting Experiment 28.

## 4. Experiment 28 identity and privacy tooling

- [ ] 4.1 Work only with synthetic populations and temporary directories.
      Do not discover, scan, hash or read personal PDFs. Preserve the
      historical Experiment 28 plan, rows, summaries, report and discussion.
- [ ] 4.2 Add `tests/test_exp28_identity_privacy.py`. Prove fail-before for ID
      reassignment after insertion/removal, legacy resume without a digest map,
      public exception-text leakage, and path-bearing setup/discovery errors.
      Use synthetic Unix, Windows and Unicode paths and chained exceptions.
- [ ] 4.3 Add the immutable private digest-to-ID map described in design D6.
      Validate schema, unique digests/IDs and study association. Persist
      privately and atomically before classification checkpoint writes.
      Do not place filenames or paths in the identity map.
- [ ] 4.4 Refuse incompatible population/schema/study/checkpoint resumes
      before classification or checkpoint mutation. Preserve identity through
      rename/reordering/duplicate copies. Refuse legacy checkpoints; do not
      infer or migrate their identity from personal files.
- [ ] 4.5 Replace public exception text and dynamic error classes with design
      D7's bounded codes. Cover discovery, hashing, reader setup, map/checkpoint
      reads/writes, classification and the top-level boundary. Keep detailed
      diagnostics in an owner-only private local sink.
- [ ] 4.6 Extend Experiment 28's local exclusions for identity, locator,
      diagnostic and temporary files. Verify private access permissions and
      safe failure if they cannot be established. No private file enters Git.
- [ ] 4.7 Record pass-after proof for every failing privacy/identity case.
      Add unchanged-population resume, duplicate-byte deduplication, corrupt
      map, failed private write, sensitive exception class and logging tests.
      Capture all public channels and assert absence of synthetic sensitive
      strings and digests. Verify detailed diagnostics stay local.
- [ ] 4.8 Run validation E's scoped Ruff, targeted pytest and Git exclusion
      checks. Verify historical hashes again. Record the tested platform and
      limitations; no personal study was executed.

## 5. Stop for operator routing decisions

- [ ] 5.1 Record the mandatory stop in the local handoff. Ask the operator
      before any later personal-PDF reading, document scanning or repeat study.
      Do not run the classifier or study summariser on the personal library.
- [ ] 5.2 Record that candidate routing selection, production routing changes,
      a mixed patch, OCR default promotion, replacement of the current policy,
      and claims from new private measurements remain unapproved and deferred.
      Synthetic test success does not satisfy these approvals.
- [ ] 5.3 Verify no production routing/default change was made. Close this
      tooling stage with a stop record, not a selected candidate.
      Continue only to final validation of the already-authorised repairs.

## 6. Final local validation

- [ ] 6.1 Run strict OpenSpec validation for this change and repository-wide
      strict validation. Fix planning syntax locally within this change.
      Report unrelated pre-existing failures without expanding scope.
- [ ] 6.2 Run scoped Ruff, all three new regression files and existing
      experiment-contract tests using validation F.
- [ ] 6.3 Run the production file-size test and the explicit changed-file
      500-line check. Split only touched experiment/test files if needed.
      Do not add size exemptions or refactor unrelated oversized files.
- [ ] 6.4 Run the full fast suite with branch coverage after the repaired
      tree is ready: `uv run --no-sync pytest -m "not slow" --cov=omrg --cov-branch`.
      Report failures, skips and coverage honestly; do not weaken gates.
- [ ] 6.5 Recheck all historical SHA-256 values, protected Git paths and
      private index inventories. Inspect the final diff for private files,
      production changes, ADR edits, abandoned Experiment 25 work and
      unrelated restoration. Preserve all evidence.
- [ ] 6.6 Report exact local/remote heads, intentional commits, validation
      commands/results, amended output locations and unresolved questions.
      Label runtime checks not executed as RUNTIME UNVERIFIED.
      Do not merge, open a PR, archive this change or synchronise NiftyPM.
