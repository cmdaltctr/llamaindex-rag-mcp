# Security Assessment: repair-input-quality-experiment-evidence (tasks 4.1-4.6)

*(Relocated 2026-09-10 from `openspec/changes/improve-rag-input-quality-5/risks.md`,
where the reviewer first wrote it, into this change's evidence directory.
The reviewed files are the nine Experiment 26/27 files changed by tasks
4.1-4.6; findings 1, 3 and 4 were fixed the same day — see
`task-4-checkpoint-repair.md` for the fix record. Finding 2 was partially
addressed (runner-imported `_lib` modules added to the run identity);
remaining provenance depth is recorded there as a limitation. Finding 5
was accepted as documented.)*

## Summary

- **Date**: 2026-09-10
- **Scope**: The nine Experiment 26 and 27 Python files named in the review request
- **Review type**: Narrow code-level review
- **Final verdict**: **NEEDS FIXES**
- **Scoped deterministic findings**: 0
- **LLM-judged findings**: 4 MEDIUM, 1 LOW

The mandatory repository scanner gate produced a global `BLOCKED` verdict with
164 findings. None referred to a file in this review scope. That global floor
is outside this narrowly bounded verdict. The user explicitly restricted the
review to the nine listed files and stated that separate scanner evidence
already exists. Bandit's SARIF formatter failed, so Bandit evidence is degraded.

## Findings

### 1. MEDIUM: Run names and output links can escape the intended directory

**Source**: [LLM-judged]

**Locations**:

- `experiments/26-query-instruction-ablation-2026-09-08/run_eval.py:114-155`
- `experiments/27-combined-candidate-path-2026-09-09/run_eval.py:124-165`
- `experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py:200,301,358-359,417-418`
- `experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py:103,220,285-286,354-355`

`run_name` is joined directly to `output/runs`. Absolute paths and `..`
segments can escape that root. Existing directory or file symlinks can redirect
checkpoint, session, manifest, JSON, or Markdown writes. The fixed `.json.tmp`
name also follows a pre-existing symlink before `replace()` runs.

**Concrete fix**:

1. Accept a single safe name component with a strict length-limited allowlist.
2. Reject absolute paths, `.`, `..`, separators, and resolved paths outside `output/runs`.
3. Reject symlinked run directories and output files.
4. Create unique temporary files in the verified destination directory.
5. Use no-follow file creation where the platform supports it.
6. Add traversal and symlink regression tests for both runners and summarisers.

### 2. MEDIUM: Run identity does not bind all executable code or session state

**Source**: [LLM-judged]

**Locations**:

- `experiments/26-query-instruction-ablation-2026-09-08/run_eval.py:207-216,331-365`
- `experiments/27-combined-candidate-path-2026-09-09/run_eval.py:217-226,347-381`
- `experiments/_lib/checkpoint_validity.py:194-252`

The identity hashes only the runner and optional lockfile. Changes to shared
validity code, retrieval metrics, the summariser, assembly logic, or project
retrieval source remain resumable. The runner also trusts `session.json`
without comparing its identity and session ID with every checkpoint. This can
mix evidence from separate executions while reporting one session lineage.

**Concrete fix**:

1. Hash every local module that affects retrieval, validation, scoring, and gates.
2. Validate `session.run_identity` against the current identity before any write.
3. Require every checkpoint session ID to match the session file when present.
4. Refuse mixed or missing session bindings for new named runs.
5. Add tests that change each bound file and mix checkpoints from two sessions.

### 3. MEDIUM: Malformed checkpoint and session shapes can crash or be rewritten

**Source**: [LLM-judged]

**Locations**:

- `experiments/_lib/checkpoint_validity.py:122-139,215-252`
- `experiments/26-query-instruction-ablation-2026-09-08/run_eval.py:145-155,172-179,348-354`
- `experiments/27-combined-candidate-path-2026-09-09/run_eval.py:155-165,182-189,364-370`

`validate_cells()` calls `.get()` and `len()` before confirming that each state
and `rows` value has the expected type. `evaluate_resume()` passes an arbitrary
`run_identity` value into set operations. Session resumption coerces unvalidated
`periods` and `interruptions`, then writes the result. These paths can crash and
can rewrite malformed state instead of rejecting it before mutation.

Runner outputs also omit `allow_nan=False`. The summarisers use it correctly,
and `classify_cell()` correctly rejects non-finite latency values.

**Concrete fix**:

1. Parse JSON through strict checkpoint, identity, and session validators.
2. Return a clear refusal before creating or changing any file.
3. Require objects, lists, strings, integers, and finite numbers at each field.
4. Use `json.dumps(..., allow_nan=False)` for every JSON output.
5. Make session and manifest writes atomic through the same validated writer.
6. Add tests for top-level arrays, null fields, invalid identities, and NaN.

### 4. MEDIUM: Non-positive smoke limits can trigger an unintended cloud run

**Source**: [LLM-judged]

**Locations**:

- `experiments/26-query-instruction-ablation-2026-09-08/run_eval.py:327-331,410-413`
- `experiments/27-combined-candidate-path-2026-09-09/run_eval.py:343-347,426-429`

The code slices only when `limit` is truthy. `--limit 0` therefore runs the
full query set. Negative limits run nearly the full set. Both cases use the
cloud embedding backend and can cause unexpected requests, retries, delay, and cost.

**Concrete fix**:

1. Reject limits below 1 in argument validation.
2. Apply an explicit maximum smoke limit.
3. Slice when `limit is not None` after validation.
4. Add tests for zero, negative, excessive, and valid limits.

### 5. LOW: Top-level `assembly` import can reuse the wrong cached module

**Source**: [LLM-judged]

**Locations**:

- `experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py:37-46`
- `tests/test_exp26_verdict_validity.py:20-27,63-70`
- `tests/test_exp27_verdict_validity.py:32-38`

Prepending `sys.path` makes the local file win normal path lookup. Python still
reuses an existing `sys.modules["assembly"]` from another package or test. The
tests also leave inserted paths behind after `runpy.run_path()`, which can alter
later test imports.

**Concrete fix**:

1. Load the local assembly module by verified file path under a unique module name.
2. Restore `sys.path` in a `finally` block after each `runpy` load.
3. Add a regression test with an unrelated preloaded `assembly` module.

## Categories With No Finding

- **Secrets and credentials**: No scoped scanner hit or manual secret found.
- **Authentication and authorisation**: N/A. These offline scripts expose no auth boundary.
- **SQL, command, XSS, and SSRF injection**: No sink found in scope.
- **PII and error leakage**: No PII found. Paths shown are operator-selected run paths.
- **Test network isolation**: Current tests neutralise dotenv and invoke no transport or network path.
- **Cloudflare Workers**: N/A. No Worker code is in scope.

## Verification

`uv run --no-sync pytest -q tests/test_exp26_verdict_validity.py tests/test_exp27_verdict_validity.py`

Result: **24 passed in 2.03s**.

## Verdict

**NEEDS FIXES**

The path-boundary, provenance, malformed-state, and smoke-limit defects require
repair before these runners are used for new cloud-backed measurements.
