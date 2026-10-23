# Tasks

## 1. Golden base output (before any code)

- [ ] 1.1 Write `tests/unit/test_mantiq_golden_base.py` with a deterministic stub answer model and stub judge; verify the file runs green on v4 HEAD with `uv run pytest tests/unit/test_mantiq_golden_base.py -q`.
- [ ] 1.2 Record the full `Engine.answer` result, timing fields removed, for three fixture questions (grounded, no evidence, verification on) in `tests/fixtures/mantiq_golden/engine_answer.json`; verify the test compares against the file and fails when one recorded field is edited.
- [ ] 1.3 Record the graph-path result of a user profile bound to the canonical answer graph in `tests/fixtures/mantiq_golden/graph_answer.json`; verify the test fails when one recorded field is edited.
- [ ] 1.4 Record the MCP `answer_documents` output for the same questions in `tests/fixtures/mantiq_golden/mcp_answer.json`; verify the test fails when one recorded field is edited.
- [ ] 1.5 Record the completion-call count of each path in the same fixtures; verify the test fails when the stub model is called once more.
- [ ] 1.6 Update `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` with a dated comment; verify `uv run pytest tests/test_clean_base_tripwire.py -q` passes.

## 2. Make room in the composition root

- [ ] 2.1 Move `request_limit_issues`, `_answers` and `_out_of_range` with their limit constants from `src/omrs/compose_pipelines.py` to `src/omrs/compose_pipeline_runs.py`, with no behaviour change; verify `uv run pytest tests/unit -k "pipeline" -m "not slow" -q` passes and `compose_pipelines.py` is under 490 lines.

## 3. Package and import boundary

- [ ] 3.1 Create `src/omrs/core/mantiq/__init__.py` with a docstring and no imports; verify `uv run python -c "import omrs.core.mantiq"` succeeds.
- [ ] 3.2 Add contract `base-never-imports-mantiq` to `pyproject.toml`: every `omrs.core` package except `omrs.core.mantiq`, plus `omrs.transports`, `omrs.config`, `omrs.integrations` and `omrs.daemon`, as sources; `omrs.core.mantiq` as forbidden; `allow_indirect_imports = true`; `unmatched_ignore_imports_alerting = "error"`; verify `uv run lint-imports` passes.
- [ ] 3.3 Verify contract 3.2 bites: add a temporary `import omrs.core.mantiq` to `core/answer/results.py`, confirm `uv run lint-imports` fails, then remove the line.
- [ ] 3.4 Add `omrs.core.mantiq` to the `core-business-avoids-providers-transports` source list; verify `uv run lint-imports` passes with no new ignore entry.
- [ ] 3.5 Add contract `mantiq-stays-out-of-retrieval-and-ingestion` (source `omrs.core.mantiq`, forbidden `omrs.core.retrieval` and `omrs.core.ingestion`, same style); verify `uv run lint-imports` passes.

## 4. Records and node parameters

- [ ] 4.1 Add frozen dataclasses `ConceptFrame`, `ClaimRecord`, `InferenceRecord` and `InferenceChecks` in `core/mantiq/records.py`, with the spec caps and `to_dict()`; verify round-trip and cap enforcement in `tests/unit/test_mantiq_records.py`.
- [ ] 4.2 Add `ConceptFrameParams`, `TasdiqParams` and `QiyasParams` in `core/mantiq/params.py` (`extra="forbid"`, frozen); verify defaults and the refusal of an unknown key in `tests/unit/test_mantiq_params.py`.

## 5. Taṣawwur: concept frame

- [ ] 5.1 Write the frame prompt and parser in `core/mantiq/concept_frame.py`; verify parse success, cap truncation, unparseable reply to skip, and no model to skip in `tests/unit/test_mantiq_concept_frame.py`.
- [ ] 5.2 Write the query augmentation rule (original text, then canonical and narrower concepts); verify the emitted text with `augment_query` on and off in the same test file.

## 6. Taṣdīq: four-verdict judge

- [ ] 6.1 Write the four-verdict prompt in `core/mantiq/tasdiq.py` with delimited evidence and an instruction hierarchy, reusing `split_claims`; verify an injected instruction inside evidence stays inside the delimiters in `tests/unit/test_mantiq_tasdiq.py`.
- [ ] 6.2 Write the verdict parser and the `conditions:` line parser (at most 8 items); verify each verdict, a missing conditions line and a malformed reply mapping to `unparseable`.
- [ ] 6.3 Build `ClaimRecord`s and apply the `authority_status` rule when rows carry the field; verify both spec scenarios (superseded evidence to `uncertain`; no labels, all supported claims are premises).
- [ ] 6.4 Verify the base judge is untouched: `uv run pytest tests/test_answer_verify.py -q` passes and `git diff --stat src/omrs/core/answer` is empty.

## 7. Qiyās: inference gate

- [ ] 7.1 Write the inference-sentence finder in `core/mantiq/inference.py` (marker words or two or more cited rows, cited or not); verify an uncited "Therefore B." sentence yields a candidate in `tests/unit/test_mantiq_inference.py`.
- [ ] 7.2 Write the labelling prompt and parser for `inference_type` and premise structure (antecedent, consequent, disjuncts, quantity words, modal markers); verify each of the five forms and `unclassified` from fixture replies.
- [ ] 7.3 Write the checks in `core/mantiq/checks.py`; verify every scenario of "Inferences are typed, checked and validated" with model-free tests in `tests/unit/test_mantiq_checks.py`.
- [ ] 7.4 Verify the checks bite: stub each check to return `True` in turn and confirm its test fails.
- [ ] 7.5 Write the modal scale, quantity scale and exhaustiveness markers as module constants with docstrings citing the spec; verify `may` to `must` rejected, `must` to `may` allowed, `some` to `all` rejected, and `only` sets exhaustive.

## 8. Answer gate

- [ ] 8.1 Write `core/mantiq/gates.py` to build `mantiq.claims`, `mantiq.inferences`, `mantiq.rejected`, `mantiq.outcome` and `mantiq.original_answer`; verify the three answer-gate scenarios in `tests/unit/test_mantiq_gates.py`.
- [ ] 8.2 Verify the gate never changes `status`, `citations`, `evidence`, `verified`, `unverified_claims` or `verification_skipped`, with a test that compares those keys before and after.

## 9. Graph operations

- [ ] 9.1 Write the three descriptors and adapters in `core/mantiq/graph_adapters.py`, modelled on `verify.claims`, each with a `BypassSpec`; verify ports, parameters and bypass in `tests/unit/test_mantiq_graph_adapters.py`.
- [ ] 9.2 Make the judge adapters call `context.resource("verify_llm")` with a copy of the answer block that has `verify_claims=True`; verify with a fake resource that the copy reaches the factory.
- [ ] 9.3 Make a missing resource, a `None` judge or a raising factory report `outcome="skipped"` with a reason and return the answer unchanged; verify all three cases.
- [ ] 9.4 Record `calls`, `elapsed_ms`, `outcome` and, for the frame node, the frame in each node summary; verify the summary keys.
- [ ] 9.5 Add `register_mantiq_operations(catalogue)` and call it in `build_operation_catalogue`; verify `uv run pytest tests/unit/test_pipeline_templates.py -q` passes and `compose_pipelines.py` stays at or under 500 lines.

## 10. Template

- [ ] 10.1 Write the `answer-mantiq` transform and the named experiment cells in `core/mantiq/templates.py`; verify node order, the bypassed `verify.claims`, and that synthesis keeps the original `query` input in `tests/unit/test_mantiq_templates.py`.
- [ ] 10.2 Add `mantiq_templates(engine)` to `src/omrs/compose_templates.py`; verify the template passes `engine.validate_pipeline` for hybrid and plain hosts.
- [ ] 10.3 Append `answer-mantiq` to `describe_templates` in `transports/api/routes/templates.py`, with an `OUTPUT_DESCRIPTIONS` entry; verify the three canonical entries are unchanged.
- [ ] 10.4 Add `answer-mantiq` to the `PipelineTemplate.name` enum and the optional `mantiq` block to `AnswerResponse` in `openapi.yaml`; verify `uv run pytest tests/test_openapi_conformance.py -q` passes.
- [ ] 10.5 Update `tests/unit/test_web_templates.py` to expect the canonical templates then `answer-mantiq`; verify it passes.
- [ ] 10.6 Verify `canonical_templates()`, `TEMPLATE_NAMES` and `profile_templates()` are unchanged with `uv run pytest tests/unit/test_pipeline_templates_parity.py tests/unit/test_hybrid_shape_parity.py -q`.
- [ ] 10.7 Run a user profile bound to the `answer-mantiq` template end to end with stub models; verify the result carries a `mantiq` block and an unchanged `status`.

## 11. Web workspace

- [ ] 11.1 Load the `omrs-design` skill and read `web/DESIGN.md`; verify the plan for 11.2 to 11.5 uses only `components/ui/` primitives and tokens.
- [ ] 11.2 Add a `listPipelineTemplates` client in `web/src/api/pipelines.ts`; verify its unit test calls `/v1/pipeline-templates`.
- [ ] 11.3 Add "Use the manṭiq answer template" to the Answer pipeline of a user profile in the Studio canvas; verify a test loads the graph into the draft and the gallery still makes no template call (`StudioView.test.tsx`).
- [ ] 11.4 Add the optional `mantiq` type to the answer result in `web/src/api/documents.ts`; verify `npm run typecheck` passes in `web/`.
- [ ] 11.5 Show the `mantiq` outcome, rejected sentences with failing checks, and the skip reason in the chat turn; verify a test with and without a `mantiq` block.
- [ ] 11.6 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`; verify all three pass.
- [ ] 11.7 Check the Studio action and the chat block in a browser at 1280 px and 390 px, in light and dark themes; verify four screenshots show no overflow or contrast failure.

## 12. Docs

- [ ] 12.1 Add the three operations to the operation table in `docs/guides/pipelines.md`; verify `uv run pytest tests/unit/test_pipeline_guide.py -q` passes.
- [ ] 12.2 Write `docs/guides/mantiq-reasoning-gates.md` (how to bind the template, node parameters, the `mantiq` block, cost, known limits); verify every path it names exists.
- [ ] 12.3 Add one line to `docs/guides/mcp-tools.md` that an answer may carry a `mantiq` block; verify the line names the template.

## 13. Experiments (design D10)

- [ ] 13.1 Map the 120 Experiment 20 triples to four verdicts by attack class into `experiments/44a-tasdiq-judge-comparison-<date>/ground-truth.json`, leaving Experiment 20's file unchanged; verify the class counts match Experiment 20.
- [ ] 13.2 Review every mapped label by hand and record changes with reasons; verify the review log lists all 120 triples.
- [ ] 13.3 Have a second annotator label a stratified 40-triple sample blind; verify agreement (Cohen's kappa) is recorded before any judge run.
- [ ] 13.4 Write 60 new triples with modal qualifiers and their gold conditions; verify the counts per verdict are recorded.
- [ ] 13.5 Decide with the user whether 44A adds NLI or small decision-model rows, using authority-aware-retrieval tasks 9.1 and 9.2; verify the decision and its reason are recorded in the 44A notes.
- [ ] 13.6 Write the 44A protocol from `experiments/EXP_PROTOCOL_TEMPLATE.md`, with cells as named templates and extra model rows only as decided in 13.5; verify the `experiments/_lib/plan.py` validator passes.
- [ ] 13.7 Run 44A with checkpoint and resume; verify `results.md` reports every gate value and the judge decision.
- [ ] 13.8 Build the 44B item set (150 to 200 items, per form: valid, matching fallacy, non-exhaustive disjunction, strengthened qualifier, strengthened quantity, surplus content) with a development / test split; verify the counts per category in `ground-truth.json`.
- [ ] 13.9 Write the 44B gold labels before any gate run; verify each item has a form label and an expected validity status.
- [ ] 13.10 Have a second annotator check 40 44B items blind; verify agreement is recorded before any gate run.
- [ ] 13.11 Run 44B and write `results.md` with labelling accuracy, per-check precision and recall, invalid rejection and valid false rejection; verify the report names failing check classes if a gate fails.
- [ ] 13.12 Confirm Experiment 35A has run and its results exist; verify the path is recorded before 44C starts.
- [ ] 13.13 Create and run `experiments/44c-concept-frame-ablation-<date>/` (raw, multi-query, HyDE-style, concept frame) on the 35A subset plus the 40-question ambiguity set; verify `results.md` reports recall@10 and nDCG@10 per cell and the 5-point gate.

## 14. Decision record and close-out

- [ ] 14.1 Write `docs/adr/091-mantiq-reasoning-gates.md` (plugin design, chosen judge, what the 44C result means for the frame); verify it links the three results files and is listed in `docs/adr/ADR_README.md`.
- [ ] 14.2 Rerun `tests/unit/test_mantiq_golden_base.py` with the operations registered and no profile bound to a manṭiq template; verify all three paths match their golden output.
- [ ] 14.3 Run `./scripts/local_ci.sh`; verify it passes.
- [ ] 14.4 Run `openspec validate mantiq-reasoning-gates --strict`; verify it passes before the PR to `v4`.
