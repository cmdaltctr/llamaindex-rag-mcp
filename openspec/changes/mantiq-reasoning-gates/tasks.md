# Tasks

## 1. Make room in the answer pipeline (design D7)

- [ ] 1.1 Move `_base_result`, `_zero_generation_diagnostics` and the three error-result blocks from `core/answer/pipeline.py` to a new `core/answer/results.py` with no behaviour change; verify `uv run pytest tests/test_answer_*.py -m "not slow" -q` passes unchanged and `pipeline.py` is under 420 lines.

## 2. Settings and layering

- [ ] 2.1 Add `core/reasoning/settings.py` with `ReasoningSettings` (`concept_frame_enabled=False`, `inference_gate_enabled=False`, `judge="seam"`) and nest it as `AnswerSettings.reasoning`; verify `ANSWER__REASONING__INFERENCE_GATE_ENABLED=true` resolves through `get_settings()` and a profile YAML override wins, in a new `tests/test_reasoning_settings.py`.
- [ ] 2.2 Add `omrg.core.reasoning` to the `core-business-avoids-providers-transports` and `settings-models-are-pure-data` contracts in `pyproject.toml`; verify `uv run lint-imports` passes with no new ignore entries.
- [ ] 2.3 Add the three env keys to `.env.example` and `docs/guides/configuration.md`; verify `tests/test_env_example*.py` (or the existing env-doc drift test) passes.

## 3. Data model

- [ ] 3.1 Add frozen dataclasses `ConceptFrame`, `ClaimRecord`, `InferenceRecord`, `InferenceChecks` in `core/reasoning/` with the field caps from the spec and `to_dict()` helpers; verify round-trip serialisation and cap enforcement in `tests/test_reasoning_models.py`.

## 4. Taṣdīq: extend the ADR-059 judge

- [ ] 4.1 Add `verdict_mode` to `verify_claims()` / `build_judge_prompt()` / `parse_verdict()` with `"two_way"` default; verify the two-way prompt is byte-identical to the current prompt by snapshot test in `tests/test_answer_verify.py`.
- [ ] 4.2 Implement four-way parsing (`supported`, `contradicted`, `unsupported`, `uncertain`) plus a `conditions:` line parser capped at 8 items; verify with parser unit tests covering each verdict, missing conditions line, and malformed replies mapping to `unparseable`.
- [ ] 4.3 Build `ClaimRecord`s from four-way verdicts and apply the `authority_status` downgrade rule when rows carry the field; verify both spec scenarios (superseded evidence → `uncertain`; no labels → all supported claims eligible) in `tests/test_reasoning_premises.py`.

## 5. Taṣawwur: concept frame

- [ ] 5.1 Implement `concept_frame.py`: prompt builder requesting a fenced JSON frame, parser with caps, and `build_concept_frame(query, seam)` returning a frame or a skip reason; verify parse success, cap truncation, unparseable → skip, and no seam → skip in `tests/test_reasoning_concept_frame.py`.
- [ ] 5.2 Wire the frame into `answer()` before retrieval when `concept_frame_enabled`; pass include terms, exclude terms and scope to the existing search call as query augmentation and filter hint; verify with a stub seam that the search call receives the data and the result carries `concept_frame`, and that with the flag off the search call and result are unchanged.

## 6. Qiyās: inference gate

- [ ] 6.1 Implement the labelling prompt and parser in `inference.py` for `inference_type` and premise structure (antecedent, consequent, disjuncts, modal markers); verify each of the five forms and `unclassified` parse from fixture replies.
- [ ] 6.2 Implement the deterministic checks (`premises_supported`, `form_valid`, `no_affirmed_consequent`, `no_denied_antecedent`, `alternatives_exhaustive`, `qualifiers_preserved`, `no_surplus_content`) and the validity rule; verify every spec scenario in the "Inferences are typed" requirement with model-free unit tests in `tests/test_reasoning_inference.py`, and verify each test fails when its check is stubbed to `True`.
- [ ] 6.3 Implement the modal-strength ordinal scale and the exhaustiveness marker list as module constants with docstrings citing the spec; verify boundary cases (`may` → `must` rejected, `must` → `may` allowed, `only` marker sets exhaustive).

## 7. Answer gate and result block

- [ ] 7.1 Implement `gates.py`: filter answer sentences to supported claims and valid inferences, build `reasoning.claims`, `reasoning.inferences`, `reasoning.rejected`, and `reasoning.original_answer` on total rejection; verify the three spec scenarios including `status="generation_unverified"` when nothing survives.
- [ ] 7.2 Wire the gate into `answer()` after verification and before the status decision; verify the status set is unchanged (`tests/test_answer_core.py` status enumeration test) and that with the flag off the result has no `reasoning` key and the same completion-call count.
- [ ] 7.3 Add `concept_frame_ms`, `inference_ms`, `concept_frame_calls`, `inference_calls` to diagnostics only when the respective gate ran; verify presence and absence per the spec scenarios.

## 8. Judge pluggability

- [ ] 8.1 Add `compose_answer.build_reasoning_judge(answer_block)` returning the seam for `judge="seam"` and lazily importing `integrations/decision_onnx.py` or `integrations/nli.py` otherwise; verify a missing runtime raises at composition with the message naming `ANSWER__REASONING__JUDGE` and the extra, in `tests/test_answer_compose.py`.
- [ ] 8.2 Implement `integrations/decision_onnx.py` (Julia 1 adapter: closed-choice request → option index and probabilities → text protocol reply with `judge_confidence`) behind an optional extra; verify with a fake ONNX session that the adapter emits a parseable four-way reply.
- [ ] 8.3 Implement `integrations/nli.py` (cross-encoder adapter mapping entailment / contradiction / neutral to the four-way verdict with an `uncertain` band) behind an optional extra; verify the mapping table and band with unit tests.
- [ ] 8.4 Smoke-test the Julia 1 ONNX export under ONNX Runtime in Python from a scratch script and record the outcome in the 44A protocol; verify by a recorded run log (pass or documented failure).

## 9. Transports and docs

- [ ] 9.1 Surface the `concept_frame` and `reasoning` blocks in `transports/mcp/answer.py` and the CLI answer command without new tools; update the tool description with the cost statement; verify `tests/test_answer_transport_mcp.py` and `tests/test_answer_transport_cli.py` cover flag-on and flag-off output.
- [ ] 9.2 Write `docs/guides/reasoning-gates.md` and update `docs/guides/mcp-tools.md`; verify the docs drift check (grep of setting names) finds every new key documented.

## 10. Experiments (design D9)

- [ ] 10.1 Create `experiments/44a-tasdiq-judge-comparison-<date>/` from the protocol template: freeze the 120 Experiment 20 triples plus 60 new modal-qualifier triples, define cells (seam, `onnx_decision`, `nli`, lexical) and gates; verify `protocol.md` passes the experiment validity checklist before any run.
- [ ] 10.2 Run 44A with checkpoint/resume and write `results.md`; verify all gate values are reported with the decision (which judges are viable locally).
- [ ] 10.3 Create `experiments/44b-inference-form-benchmark-<date>/`: build the 150 to 200 item set (per form: valid, matching fallacy, non-exhaustive disjunction, strengthened qualifier, surplus content), with a development / test split; verify the item counts per category and the split are recorded in `ground-truth.json`.
- [ ] 10.4 Run 44B and write `results.md` reporting labelling accuracy, per-check precision and recall, invalid rejection rate and valid false rejection rate against the gates; verify the report names the failing check classes if any gate fails.
- [ ] 10.5 Create and run `experiments/44c-concept-frame-ablation-<date>/` (raw, multi-query, HyDE-style, concept frame) on the Experiment 35A subset plus the 40-question ambiguity set; verify `results.md` reports recall@10 and nDCG@10 per cell and the ambiguity-set delta against the 5-point gate.

## 11. Decision record and close-out

- [ ] 11.1 Write the ADR for the reasoning gates (decision on default state per profile, chosen judge, and what the 44C null or positive result means for the concept frame) in `docs/adr/`; verify it links the three results files and is listed in `ADR_README.md`.
- [ ] 11.2 Apply any `documents.yaml` override the ADR authorises; verify the profile test asserts the override and `codebase.yaml` remains off.
- [ ] 11.3 Run `./scripts/local_ci.sh` and `openspec validate --change mantiq-reasoning-gates --strict`; verify both pass before the PR to `v4`.
