## Context

The starting point is commit
`afe151e93dd9b79e18618811dc15e35c6a96b16d` on
`feat/repair-input-quality-evidence-v2`, based on `v3`.
`openspec/config.yaml` selects `spec-driven`; neighbouring changes use
`.openspec.yaml`, proposal, design, delta specifications and tasks.
The root `.openspec.yaml` lookup returned no file; configuration is under
`openspec/`, and change metadata belongs inside the change directory.

Relevant evidence and conventions:

| Area | Existing files | Consequence |
| --- | --- | --- |
| General validity | `openspec/specs/experiment-validity-gates/spec.md`, TDR-014, `experiments/_lib/{plan,preflight,stats,manifest}.py` | Reuse applicable checks; do not invent historical observations. |
| Experiment 25 | `25-token-chunking-ablation-2026-09-08/{build_index.py,results.md,plan.json}`, TDR-022/023, ADR-063 | Preserve COMPLETE PASS and the unconditional refusal. |
| Experiment 26 | `26-query-instruction-ablation-2026-09-08/{run_eval.py,summarise_eval.py,discussion.md,output/}` | Validate full query membership and provenance before verdicts. |
| Experiment 27 | `27-combined-candidate-path-2026-09-09/{run_eval.py,summarise_eval.py,plan.json,output/}` | Validate reference cells as well as measured cells. |
| Experiment 28 | `28-pdf-classification-prevalence-2026-09-09/{classify.py,.gitignore,protocol.md}` | Persist identity before checkpoint use; separate public and private errors. |
| Decisions | ADR-064 | Preserve decisions; document evidence qualifications separately. |
| Validation | `tests/test_file_size_ceiling.py`, experiment contract tests | The existing size test covers production Python only; check changed planning and experiment files separately. |

Experiment directory names in the table are relative to `experiments/`.

## Goals / Non-Goals

Goals:
- Preserve historical bytes and identify every input used for an amendment.
- Refuse verdicts based on incomplete, incompatible or unsupported evidence.
- Repair each experiment independently, with fail-before and pass-after proof.
- Make Experiment 28 identity stable and its public errors non-sensitive.

Non-goals:
- Reopen Experiment 25, rebuild indexes or perform paid repeats.
- Repair production retrieval, routing, embedding or OCR behaviour.
- Change frozen thresholds, instructions, original protocols or ADRs.
- Introduce dependencies, a recovery framework or paid-run infrastructure.
- Read personal PDFs or select an OCR policy during this change.

## Decisions

### D1. Freeze the historical evidence boundary

Before implementation, the local agent records a SHA-256 inventory of original
plans, protocols, raw checkpoints, manifests, summaries, reports, discussions
and relevant baseline inputs. Record the base commit and lockfile hash too.
Keep a private inventory for preserved external indexes; do not traverse or
hash personal PDFs for Experiment 28.

Protect all Experiment 25 files, ADR-063/064, the original
`improve-rag-input-quality-5` planning files, and historical evidence under
Experiments 26–28. Hashes must match after each relevant stage and at final
validation. A mismatch stops the stage; do not silently refresh the baseline.
Index preservation checks are read-only. No ingestion, compaction, deletion
or index migration is part of the repair.

The Experiment 25 close-out is an additive `close-out.md` under this new
change directory during later implementation. It records the operator's
declined rerun and retained COMPLETE PASS. No Experiment 25 code or new
Experiment 25 test is required.

### D2. Verify recovery provenance before selecting files

The local recovery source supplied by the operator is:

`/Users/aizat/Development/PROJECTS/input-quality-recovery-468391ac-20260910/recovered-files`

This path is a local handoff input, never a program default. ChatGPT cannot
inspect it. The local agent lists candidates without extracting an archive over
the checkout. For each candidate, compare its bytes and intended role against
the base commit and current tree. Record source identifier, source SHA-256,
destination, destination hash, differences, selection decision and rationale.

Keep absolute paths and sensitive details in a private local ledger. A public
repair record uses repository-relative paths or opaque recovery identifiers.
Do not restore symlinks that escape the selected source, path-traversal
entries, private manifests, indexes, credentials, unrelated files, or abandoned
Experiment 25 work. Restore only individually reviewed Experiment 26/27 repair
code or tests. Test them against the unfixed baseline before accepting them.

Recovered historical evidence goes to a separate amendment input directory,
with an explicit origin label. It does not overwrite committed originals.
A different hash does not establish corruption or correctness by itself.
If provenance cannot be established, mark the candidate unverified and do
not use it to support a verdict. Do not reconstruct unavailable content.

### D3. Validate evidence before calculating a decision

Use small pure helpers local to each experiment. Reuse existing plain-data
helpers where their schema matches. Do not refactor all experiment runners.

For Experiment 26, require both `raw_none` and `candidate_instruction`.
For Experiment 27, require `chunking_only_raw`, `combined_candidate`,
`baseline_production` from Experiment 22 and `instruction_only` from
Experiment 26. Keep each cell's role and source explicit.

Load the frozen ground truth before creating a query dictionary, so duplicate
ground-truth IDs cannot disappear. Require the expected 223 IDs and category
membership (200 identifier-heavy, 3 semantic, 20 continuity). Each required
checkpoint must contain exactly one row per expected ID. Reject unknown,
duplicate, missing or mismatched IDs, inconsistent categories, duplicate
`done` entries and disagreement between `done` and row IDs.
Do not silently intersect arms or substitute a reference for a missing arm.

Require well-formed ranked parent-ID lists and finite non-negative measured
latencies. An empty retrieval ranking can be a valid zero-quality result;
missing rankings, malformed rows, NaN, infinity and recorded execution errors
are invalid evidence. Incomplete smoke data must not receive a full-study
verdict. Validate required gate kinds, comparators and thresholds against the
frozen plan; missing or duplicate gates must not pass through `all([])`.

Evidence status is separate from performance:
- `COMPLETE`: all required evidence is admissible.
- `INCOMPLETE`: required observations are absent.
- `INVALID`: identities, structure or provenance conflict.

Only COMPLETE evidence may produce a current PASS or FAIL performance verdict.
Otherwise write a separate diagnostic assessment with `verdict: null`,
reasons and a non-zero exit. Do not manufacture zero metrics or label an
interrupted run a negative performance result.

### D4. Distinguish historical observation from present inspection

Use TDR-014's mandatory evidence fields as the admissibility checklist:
historical commit and lock identity; corpus/query/qrel/index identities;
effective embedding provider/model; vector-store backend/mode/score kind;
retrieval settings and effective sparse backend for hybrid cells; applicable
plan assertions and completion evidence. Missing information is explicit.

The existing Experiment 26/27 manifests declare constants and lack much of
this provenance. Do not backfill them using the current environment.
An authenticated historical log or recovery artefact can supply a fact only
when its provenance links it to the same run and checkpoint. Record that link.
Current index metadata is labelled a later observation; it does not prove
historical execution. Source intent and equal aggregate values do not prove
endpoint determinism or actual provider execution.

Historical rows may still support clearly labelled descriptive recomputations
when runtime provenance is incomplete. Such tables carry the evidence status
and cannot become a fresh admissible PASS or a new promotion claim.

Use full SHA-256 hashes of actual inputs, rather than the abbreviated qrels
prefix in old prose. Record algorithm, input identifier, byte count and digest.
A present-day digest proves the bytes used now, not a timestamped historical
measurement. Keep original run dates, when evidenced, separate from
`recomputed_at` and `repair_commit`.

### D5. Write amendments separately and preserve metric meaning

Give each Experiment 26/27 summariser an explicit `--amendment-dir` and
`--evidence-manifest` input. The evidence manifest records the selected
inputs, hashes, roles and provenance assessment. Relative paths resolve from
the manifest location. The historical files remain read-only.

The output directory must be new and empty, outside the historical output
tree, and must not alias a protected path through symlinks. Refuse an existing
destination. Write `assessment.json`, `results.md` and `provenance.json`
there. Invalid evidence produces only an honest assessment/report, with no
performance verdict. Do not append the old `discussion.md` automatically.

Gate comparisons use full-precision means and the existing percentile method.
Round display fields only. Keep metric definitions, frozen thresholds, query
membership and Experiment 26's bootstrap seed/repetition count unchanged.
Add tests just below and above each relevant threshold to expose pre-rounding.

Amended Experiment 26 prose must qualify the claims that aggregate equality
proves endpoint determinism and that execution was independently verified.
Keep the recorded historical negative result visible.

Amended Experiment 27 prose must distinguish the two earlier reference cells
from the two historical measured cells. The interaction remains descriptive
across dates and indexes. A present recomputation is not a fresh run or a
measured provider bill. Token counts are offline diagnostics, with tokenizer
identity and counting date; unavailable cached tokenisation remains unavailable,
without downloading a model. Do not claim that 446 query rows prove exactly
446 billed requests or retries. OCR was not exercised by the FreshStack study.

Do not use Experiment 27's current `_drift` fallback to an arbitrary first cell.
Require the named Experiment 25 reference cell and verified summary input;
absence yields an unavailable diagnostic, never a substituted measurement.
Experiment 25's historical verdict remains unchanged.

### D6. Freeze a private identity map for Experiment 28

Introduce a small experiment-local identity helper. For a new, separately
authorised study, deduplicate content by full SHA-256 and assign opaque
sequential IDs once. Persist the complete mapping before any classification
checkpoint can be written. The private map contains a schema version, opaque
study identifier and digest-to-ID entries. It contains no filenames or paths.
Keep the separate ID-to-path locator private; it is not the identity source.

Persist the identity file under a local-only name such as
`output/.local_identity.json`, alongside the existing
`output/.local_manifest.json`. Both and any temporary files must be ignored
and restricted to the operator. Use owner-only permissions where supported;
the local agent verifies the actual platform. Fail safely if private storage
cannot be established. Use an atomic, exclusive initial publication and never
replace an existing identity map.

Resume loads the stored map first. Compare the exact unique digest population,
schema, study identifier and checkpoint association. A renamed or duplicate
copy with identical bytes preserves identity. Added, removed or changed bytes,
duplicate ID assignments, corruption, or a missing map with existing
checkpoints must refuse resume. A changed population needs a separate
operator-approved study; do not renumber, extend or migrate the old map.

Bind checkpoints to the opaque study identity. Validate checkpoint IDs against
the private map before skipping completed rows. Legacy checkpoints have no
verified digest map: refuse, preserve them and explain with a public code.
Never infer the original digest map from current personal files.

The present implementation and tests use injected synthetic populations and
temporary directories. They do not call the personal-library discovery path.

### D7. Bound every public error surface

Public means shareable checkpoints, reports, stdout, stderr and normal logs.
Serialise public errors from an allowlist, not from exception strings,
exception class names or exception attributes.

Use fixed codes: `IDENTITY_MISSING`, `IDENTITY_INCOMPATIBLE`,
`IDENTITY_INVALID`, `PRIVATE_STORAGE_UNAVAILABLE`, `INPUT_UNAVAILABLE`,
`CLASSIFICATION_FAILED`, `OUTPUT_FAILED`, and `INTERNAL_ERROR`.
Messages are fixed explanatory strings. A valid opaque document ID may be
included; unvalidated strings may not. Digests remain private.

Cover discovery, hashing, missing roots, map/checkpoint parsing and writes,
reader construction, classification, logging and the top-level exception
boundary. Suppress sensitive chained tracebacks in public output. If detailed
diagnostics are needed, write them only to the owner-only local diagnostic
file, excluded together with temporary files. If that write fails, return a
bounded code without printing its error or path.

Test Unix, Windows and Unicode synthetic private paths, nested exception
causes and a custom exception with a sensitive class name. Capture stdout,
stderr, logs and public JSON. Verify no private filename, directory, digest,
text snippet or exception payload escapes. Verify diagnostics remain in the
private sink, including on failure.

### D8. Keep the operator gate separate from tooling verification

No personal discovery or reading is needed to repair or test these functions.
The local agent records the stop after synthetic verification and reports
which decisions remain unapproved. Approval of this planning change or its
tooling is not approval to study personal files or alter routing.

Before any later personal-file access, repeat study, candidate selection,
mixed patch, production policy change, default promotion, policy replacement
or new measurement claim, obtain explicit operator approval for that action.
Use a separately agreed study scope. Do not add a general authorisation system.

Stage 6 may run the fast suite and offline evidence checks while this gate
remains closed. Do not run Experiment 25, Experiment 26/27 live evaluators,
Experiment 28 classifier CLI or its study summariser during this change.

## Risks / Trade-offs

- Recovery evidence may be absent or incomplete. An explicit unresolved
  provenance assessment is preferable to invented verification.
- Stricter checks can refuse old evidence. Preserve historical verdicts and
  show the present admissibility assessment alongside them.
- Atomic private storage and permissions differ by platform. Verify them
  locally; GitHub inspection cannot establish them.
- Synthetic tests prove tooling behaviour on controlled inputs only. They
  provide no evidence for a production OCR policy.

## Migration Plan

Implement stages 1–6 in `tasks.md`. Keep every historical artefact unchanged.
Do not migrate Experiment 28 legacy checkpoints in place. Roll back a tooling
repair by reverting its code/test commit; retain evidence and repair records.
Do not delete original or amended evidence during rollback.

## Open Questions

- Which Experiment 26/27 recovery candidates have verifiable origin? The local
  agent must inspect them individually before selecting any.
- Can historical effective-runtime facts be recovered? If not, retain an
  INCOMPLETE provenance assessment and descriptive historical measurements.
- Which later Experiment 28 study and routing decisions will the operator
  approve? They remain outside this change.
