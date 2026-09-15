# Tasks: Pin Magika and correct content-detection parsing

## Historical worker progress

- [x] 1.1 Write a failing test: in the current environment `_is_magika_available()` is False (no binary) — the new "standard install detects by content" test asserts a Magika-modelled label for a probe file and FAILS before the dependency lands.
- [x] 1.2 Write a test asserting the smoke tool cannot import `ingest_path_async` (mechanical no-re-ingest constraint) and that running it over fixture paths produces a label comparison without any store/embedding call.

The checked lines are historical worker progress. Their original claims do
not establish revised parser, normalisation, or smoke coverage. Preserve the
existing worker files unchanged in this planning session.

## Implementation precondition

Before later implementation, record a path-scoped baseline and diffs.
`adad033` is the pre-pin dependency reference. Preserve the settings-injection
fix in `3dd89f7`. Do not blindly restore either ancestor or use dirty
`pyproject.toml` or `uv.lock` as a baseline.

## 1. Fail-first regressions

- [x] 1.3 Add parser regressions for nested `result.value.output`, non-`ok` status, non-JSON rows, malformed successful rows, invalid required fields, and ignored blank lines. Prove each new assertion fails before the parser change and passes afterwards. Verify one whole-scan warned suffix fallback, never fabricated labels or partial success.
- [x] 1.4 Add boundary-normalisation regressions. Verify renamed ZIP content becomes `binary/*` before a reader runs. Verify `document`, `code`, and `text` groups with `is_text=false` remain their groups. Cover only the Markdown and TXT aliases. Verify a valid PDF reaches a stub reader. Prove new assertions fail before normalisation and pass afterwards.
- [x] 1.5 Extend existing fake-store and mock-reader ingestion tests. Use substantial valid Python in a deliberately misnamed fixture. Verify `code/python` drives the existing AST-splitter machinery. Retain injected-settings and no-global-read coverage for direct-file keys, including `.`. Do not use a live store, production embedder, or short source fixture.
- [x] 1.6 Revise the historical mixed note plus disguised-Python smoke expectation: report its changed label and exit non-zero. Add a separate complete all-match fixture that exits zero. Add missing, extra, duplicate, and reordered scanner-path cases. Prove every new assertion fails before the smoke change and passes afterwards.
- [x] 1.7 Add static AST and isolated-process import guards. Permit `scan_with_suffix` from `core.codebase.codebase_map` and the corrected Magika scanner. Permit `FileEntry` or settings data only when needed. The static guard catches `build_codebase_map` and Engine symbols. The isolated blocker bans only ingestion, store, embedder, and composition-root modules. It must detect direct, transitive, and dynamic forbidden imports and be mutation-sensitive.

## 2. Small implementation

- [x] 2.1 Ask permission to install or synchronise dependencies. Change `magika>=1.0.3` to `magika==1.0.3`, then update the lock only in that authorised session. Verify the package and executable resolve to 1.0.3. Do not add `google-magika`.
- [x] 2.2 Fix the existing CLI parser and its caller's fallback catch. Accept `status == "ok"`, parse `result.value.output`, validate non-empty string `group` and `label` plus boolean `is_text`, and ignore blank lines. Raise `ValueError` for non-`ok`, non-JSON, malformed, or bad-field rows. Add `ValueError` to the existing `detect_file_types` fallback catch and verify task 1.3 passes. Preserve injected settings, one CLI transport, timeout, and warned fallback. Do not add expected-path discovery or another walker.
- [x] 2.3 Add the boundary rule: set `group="binary"` only when `is_text is False` and `group not in {"document", "code", "text"}`. Preserve label and `is_text`. Do not change pipeline skip logic, extension admission, graph semantics, or source taxonomy.
- [x] 2.4 Add only `text/markdown → document/markdown` and `text/txt → document/text` normalisation. Keep detected PDF and Python labels unchanged. Do not consult suffixes, edit `_SUFFIX_MAP`, add aliases, relabel rows, or backfill identities.
- [x] 2.5 Add `scripts/magika_label_smoke.py` after the regressions are red. Reuse existing `scan_with_suffix` and direct corrected Magika scanning. Pass injected settings to both scanners; reuse `FileEntry` only when needed. Do not copy the suffix table or add a walker. Preserve existing suffix traversal exclusions and limits. Compare path sets and labels. Retain the listed JSON fields. Fail non-zero for empty input, detector failure, invalid records, missing, extra, duplicate paths, or label mismatch. Do not call `build_codebase_map`, Engine, ingestion, embedding, store, or composition-root APIs.
- [x] 2.6 Run focused new and affected regressions after implementation. Confirm fail-before and pass-after evidence. Base-install tests MUST fail when the package is absent; do not skip them. Simulate binary absence only in fallback tests.
- [x] 2.7 Update dependency-floor tests only if the exact pin makes their measured rule require it. Do not add a speculative exemption; the exact pin has zero version gap.

## 3. Real-corpus gate

- [x] 3.1 Before execution, freeze a real acceptance corpus of representative common PDF, Python, Markdown, and TXT paths. Predesignate deliberately misnamed and tiny-source diagnostic probes separately. Record both path sets before any output exists. Do not move or exclude an acceptance file after output is known.
- [x] 3.2 Run every path set through the same smoke and detector after implementation. Record command, executable, exact package and pin, elapsed detection, coverage, counts, mismatches, and diagnostic limitations. Each diagnostic mismatch remains non-zero and is recorded separately. The frozen acceptance corpus passes only on a complete, non-empty all-match result with zero exit. STOP AND REPORT the complete findings, then execute the Undo plan for any acceptance mismatch, fallback, error, empty input, or missing, extra, or duplicate path. Do not retry, ingest, or merge.

## 4. Evidence, decision records, and guarded verification

- [ ] 4.1 After gate pass, ask authorisation before fast-suite and `scripts/local_ci.sh` checks. Existing isolated fixtures and doubles may run. Operator corpora, re-ingest, external models, and production stores must not run. Run `openspec validate pin-magika-detection --strict`. Measure existing CI tripwire executed and skipped counts. Re-baseline measured counts only.
- [ ] 4.2 After gate pass, load `s-adr` and create the success ADR. Cross-reference TDR-025. Record `magika`, retained executable override, narrow normalisation, failure behaviour, smoke evidence, fallback reality, short-source limits, and the verified ONNX-runtime and no-base-PyTorch rationale. Use elapsed detection from the smoke as the measured cost. Do not create a separate benchmark or claim isolated model-startup time.
- [ ] 4.3 After gate pass, update TDR-025 and Experiment 31 limitations without rerunning experiments. Correct historical `google-magika` and taxonomy wording. Explain the packaged CLI base dependency, `MAGIKA_BINARY` override, and retained fallback. Record evidence and limitations.
- [x] 4.4 Confirm no collection, embedding, or store changed. Record this with gate evidence before acceptance.

## 5. Undo plan

Status note (2026-09-16): the acceptance gate passed (exit 0, 16/16
all-match, `acceptance-corpus.md` run record), so the contingency
below never triggered. It stays unchecked by design.

- [ ] 5.1 If the implemented acceptance-corpus smoke fails, STOP AND REPORT, then execute option 2. Restore only pin-created dependency and lock changes, including the original worker's dependency delta, plus pin-created parser, tool, and test hunks from the recorded path-scoped baseline. Preserve documentation, the pre-existing `3dd89f7` settings fix, unrelated work, and red regression evidence. Ask approval only for destructive file deletion or package resynchronisation. Create a rejected ADR disposition despite the pass-gated success ADR task. Carry red regression evidence into TDR-025, then update Experiment 31 limitations and these artifacts. Keep success tasks incomplete and cancel them with an explanation. Never false-green, retry, ingest, or merge the failed feature.
