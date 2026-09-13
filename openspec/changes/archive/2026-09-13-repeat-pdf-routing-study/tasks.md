# Tasks: repeat-pdf-routing-study

This change continues work deferred from `repair-input-quality-experiment-evidence` (its section 6, dated 2026-09-10). The concrete routing defect experiment 28 exposed is already fixed by commit `9bf4810`; this study produces the preregistered evidence for the deferred OCR default-promotion decision.

Tick each task immediately after its verification succeeds. Add the evidence pointer beside the task. Leave blocked work unchecked and name the blocker. Sections 2 and 3 contain explicit operator-approval checkpoints: tooling preparation may proceed before approval, but no PDF is read, no candidate is selected and no paid or private-document work begins until the matching approval is recorded in the design decision register.

## 1. Make the classification tooling safe

- [x] 1.1 Repair checkpoint identity and private mapping preservation for PDF classification. Verify added, removed or replaced documents and a changed policy refuse unsafe resume. — `experiments/29-pdf-routing-repeat-2026-09-13/classify.py` (`_run_identity`, `_verify_digests`, `evaluate_resume`); tests `TestCollectionDiscovery`/`TestResumeSafety` in `tests/test_experiment_29_routing_repeat.py`.
- [x] 1.2 Remove unrestricted exception text from public outputs and check serialised artefacts for leaks. Verify an exception containing a synthetic private path cannot expose it in checkpoints or reports. — `_record_error`/`_assert_no_private_leak`; test `TestPrivacy`. The guard fired for real on first run (absolute path inside the run-identity code map) and the fix was committed before measurement (`6f3119e`-era).

## 2. Approve the collection and labels

- [x] 2.1 Ask the operator to approve the document list or precise selection rule, including the known book. Verify the approval is recorded privately before reading any selected PDF. — Approved 2026-09-13: 3 dev (book, Kerr, Sloman) + 14 held-out (Zotero `RAG` collection); recorded in `plan.json` and protocol decision register.
- [x] 2.2 Create a separate repeat-study directory and immutable private digest-to-ID mapping. Verify discovery processes only the approved collection and leaves experiment 28's original output unchanged. — `experiments/29-pdf-routing-repeat-2026-09-13/`; `prepare_collection.py` writes `.collection.private.json` once, `--force` required to rebuild; experiment 28 untouched.
- [x] 2.3 Agree an independent page-annotation method and development/held-out split. Record labels and uncertainty; verify the known book is development evidence and held-out outcomes do not guide candidate design. — `labels.json` frozen: independent pypdf per-page assessment, all pages of all 17 documents, zero uncertain labels.

## 3. Freeze the protocol

- [x] 3.1 Ask the operator to approve missing-page tolerance, whole-file routing behaviour and enable-only zero-threshold behaviour. Record the precise candidate and acceptance criteria; stop if undecided. — Approved 2026-09-13: 10% tolerance (candidate `page_fraction=0.10`), whole-file dispatch, mixed stays fast under enable-only.
- [x] 3.2 Freeze the new protocol, labels/split and criteria in a separate commit before held-out scoring. Verify the commit precedes candidate measurement; preserve all old gates. — Freeze commit `080b1fa` precedes the classification run.
- [x] 3.3 Add tests for comparing the pinned historical policy with the approved candidate, using synthetic evidence first. Verify the uncommitted patch cannot silently become the baseline and removing a guard fails its regression test. — `TestPinnedBaseline`/`TestRoutingReplay`/`TestRoutingCodeClean`: pinned set parsed from `git show afe151e`, candidate verified against committed code, dirty routing source detected.

## 4. Measure and publish

- [x] 4.1 Run the approved classification/routing evaluation and record elapsed classification time. Verify complete membership, stable resume and public-output privacy; report uncertain labels explicitly. — 17/17 classified, 0 failures, `classification_seconds` per row; re-run resumed cleanly (17 skipped); checkpoint verified free of paths.
- [x] 4.2 Record whether real OCR measurement is authorised, including selected documents, timeout and runtime budget. If authorised, add and verify explicit execution tasks; otherwise label OCR cost as projected and recovery quality unmeasured. — NOT authorised; `report.md` labels all OCR figures as projections and recovery quality as unmeasured.
- [x] 4.3 Publish the routing comparison with missing-page evidence, hold-out results and limitations. Verify fixture-based time estimates are labelled, convenience selection is disclosed, and negative results are retained. — `report.md`: vacuous held-out recall gate disclosed, enable-only Sloman miss retained, selection disclosed.
