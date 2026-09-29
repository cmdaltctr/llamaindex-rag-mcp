# Design

## Context

See proposal.md, "Why". The relevant current state:

- `core/answer/pipeline.py` (496 lines) runs retrieve → synthesise → citation
  assembly → optional verification (ADR-059) → status decision. Verification
  is `run_verification_stage()` in `core/answer/verify.py`, a two-way judge
  (`supported` / `unsupported`) over `(claim, cited evidence)` pairs produced
  by `split_claims()`. The judge is an async `CompletionSeam` injected by the
  transport; `compose_answer.build_verify_llm()` builds it.
- `AnswerSettings` (`core/answer/settings.py`) is pure data, nested under
  `Settings.answer` in `config/__init__.py` (500 lines, at the ceiling).
  Profile YAML files under `config/profiles/` may override any answer key.
- Experiment 20 measured the two-way judge: GLM-5.3 reached recall 1.0 and
  false rejection 0.0 on 120 frozen triples; a local `qwen3:4b` judge was
  infeasible; a lexical baseline scored 0.0 recall on contradicted claims.
- Paper 1 (`authority-aware-retrieval`) will add `authority_status` to
  evidence rows. It is in flight in the same worktree; nothing here imports
  it. The contract is one optional string field on a row.
- Invariants that bind this design: `core/` never imports providers or
  transports; settings are injected; no file over 500 lines; MCP handlers
  never raise; the status schema of `grounded-answer-synthesis` is closed.

## Goals / Non-Goals

**Goals:**

- Add the concept frame and inference gate as additive stages with a
  byte-identical disabled path.
- Reuse the ADR-059 stage as the Taṣdīq gate rather than adding a second
  judge loop.
- Make the judge swappable so Experiment 39A can compare the cloud seam, a
  local ONNX decision model and an NLI cross-encoder on the same inputs.
- Keep every reasoning object a frozen dataclass so results are serialisable
  and testable without a model.

**Non-Goals:**

- Implementing formal syllogistic figures and moods. The closed
  `inference_type` set is a pattern vocabulary for a validator, not a logic
  engine.
- A new MCP tool. The existing `answer` tool grows one result block.
- Changing retrieval. The frame passes include / exclude terms and scope as
  data; retrieval's use of them is limited to metadata filters and query text
  already supported.
- Training or fine-tuning any model.

## Decisions

### D1. Package location: `core/reasoning/`, not `core/answer/reasoning/`

`core/answer/` already holds nine modules and its pipeline is at 496 lines.
Nesting a sub-package under it would push the answer package towards the god
component pattern and blur the ownership of the seam. A sibling leaf package
`core/reasoning/` mirrors how `core/answer/` sits beside `core/retrieval/`:
it shares only settings and plain dicts with its neighbours. Its four files
are `concept_frame.py`, `inference.py`, `gates.py`, `settings.py`. Alternative
considered: a single `core/answer/reasoning.py`. Rejected because the frame
builder, the inference validator and the gate each need their own tests and
each will exceed 150 lines with prompts and checks.

### D2. Taṣdīq reuses `verify.py`; the four-way verdict is a prompt variant

`verify_claims()` keeps its signature. A new keyword `verdict_mode` selects
`"two_way"` (default, existing prompt, existing constants) or `"four_way"`.
Four-way mode changes only `build_judge_prompt()`'s answer instruction and
`parse_verdict()`'s accepted set, and asks the judge to append a
`conditions:` line listing the qualifiers it saw. Two-way mode is untouched so
the ADR-059 spec scenario "prompt byte-identical" holds. Alternative
considered: a second judge pass just for conditions. Rejected: doubles judge
calls for a field the same reading already produces.

### D3. The inference gate is a validator over records, and the model is only a labeller

The model (through the judge seam) does two closed-choice jobs: label each
multi-premise sentence with an `inference_type`, and extract the premise
structure (antecedent / consequent, disjuncts, universal / particular
markers) into a small schema. Every check in `InferenceRecord.checks` then
runs in Python over those labels:

- `no_affirmed_consequent` and `no_denied_antecedent`: pattern match on the
  labelled conditional and which part the second premise affirms or denies.
- `alternatives_exhaustive`: true only if the disjunctive premise's evidence
  row contains an exhaustiveness marker (`only`, `exactly one of`, `either …
  or … and no other`) or the frame's `divisions` for that concept is marked
  exhaustive. Absent both, the inference is `unverifiable`, never `valid`.
- `qualifiers_preserved`: the conclusion's modal strength (a fixed ordinal
  scale: `may` < `can` < `should` < `must` = `always`) must not exceed the
  weakest premise's strength drawn from `ClaimRecord.conditions`.
- `no_surplus_content`: named entities, numbers and conditions in the
  conclusion must appear in at least one premise text (token-level match
  after normalisation; a model is not consulted for this check).
- `premises_supported`: every `premise_claim_id` has verdict `supported`.
- `form_valid`: the labelled type is in the closed set and its premise slots
  are filled.

Rationale: the reviewer objection to any "logic gate" run by an LLM is that
the LLM grades its own homework. Putting the checks in deterministic code and
confining the model to labelling keeps the gate auditable and gives Experiment
39B a clean split between labelling accuracy and check correctness.
Alternative considered: ask the judge "is this inference valid?" directly.
Rejected for the reason above.

### D4. The concept frame is a bounded schema, not free text

`ConceptFrame` is a frozen dataclass with fixed fields and caps (12 items per
list, 512 characters per string). The seam is asked for a fenced JSON block
matching the schema; parsing failure yields `concept_frame_skipped`, never an
error status. Only three fields leave the frame: include terms (canonical
concept plus narrower concepts), exclude terms, and scope. They are passed to
the existing search call as query text augmentation and a metadata filter
hint; no new retrieval parameter is introduced in this change. Alternative
considered: a graph of concepts with the five universals. Rejected as scope
creep; the ablation in 39C decides whether the frame earns more machinery.

### D5. Premise eligibility reads `authority_status` as an optional row field

`gates.py` builds the premise set from `ClaimRecord`s. If any cited row has
`authority_status`, and all cited rows for a claim are `superseded` or
`conflicting`, the claim is downgraded to `uncertain` with a named reason.
This is a dict lookup with a default; there is no import of Paper 1's
package. Alternative considered: making Paper 1 a hard dependency. Rejected:
Paper 2 must be testable and shippable on its own, and the paper needs the
"without authority labels" baseline anyway.

### D6. Judge pluggability lives in `compose_answer.py`

`ReasoningSettings.judge` takes `seam`, `onnx_decision` or `nli`.
`compose_answer.build_reasoning_judge()` returns an async callable with the
same `prompt -> reply` shape as `CompletionSeam` for `seam`, and for the two
local options returns an adapter that maps the structured judge request
(claim, evidence texts, option list) to the model's closed-choice interface
and formats the reply in the same text protocol the parser expects. The
adapters live in `integrations/decision_onnx.py` and `integrations/nli.py`,
loaded lazily (ADR-024 pattern). A missing runtime raises at composition with
the setting name and extra. Alternative considered: a second seam type for
structured judges. Rejected: one seam type keeps the transports unchanged.

### D7. `pipeline.py` sheds its result builders before it grows

`pipeline.py` is four lines under the ceiling. Before adding two stage calls,
its `_base_result`, `_zero_generation_diagnostics` and the three error-result
blocks move to `core/answer/results.py` with no behaviour change. This is a
refactor task inside this change, done first and verified by the existing
answer tests passing unchanged.

### D8. Settings nest under `answer`

`AnswerSettings.reasoning: ReasoningSettings` keeps the env prefix
`ANSWER__REASONING__*`, keeps `config/__init__.py` at its current size, and
keeps profile override behaviour identical to `verify_claims`.
`ReasoningSettings` lives in `core/reasoning/settings.py` and is pure data
(import-linter contract `settings-models-are-pure-data` gains it).

### D9. Experiment numbering and gates

Experiment 37 is claimed by `modular-ocr-workers-dots-mocr`; 38 is reserved
for Paper 1. This change claims 39A, 39B, 39C.

- **39A Taṣdīq judge comparison.** Inputs: the frozen 120 Experiment 20
  triples plus 60 new triples with modal qualifiers (so `conditions` is
  measured). Cells: GLM-5.3 seam (reference), Julia 1 via `onnx_decision`,
  an NLI cross-encoder via `nli`, lexical baseline. Metrics: four-way
  macro-F1, unsupported recall, false rejection, conditions exact-match,
  P95 latency, cost per claim. Gate for a local judge to be recommended:
  unsupported recall ≥ 0.90 and false rejection ≤ 0.10 on the 120-triple
  subset.
- **39B Inference-form benchmark.** 150 to 200 items built from retrieved
  premises over the quality corpus and the Paper 1 authority corpus: for
  each of the five forms, valid instances, the matching fallacy, a
  non-exhaustive disjunction, a strengthened qualifier, and a surplus-content
  conclusion. Metrics: labelling accuracy per form, check precision and
  recall per check, end-to-end invalid-inference rejection rate, valid
  inference false-rejection rate. Gate: invalid rejection ≥ 0.85 with valid
  false rejection ≤ 0.15.
- **39C Concept-frame ablation.** Cells: raw query, multi-query rewrite,
  HyDE-style hypothetical passage, concept frame. Metrics: recall@10 and
  nDCG@10 on the Experiment 35A document subset plus a 40-question
  ambiguity set (terms with two corpus senses). Gate for keeping the frame
  as a first-class stage: it must beat the best rewrite baseline on the
  ambiguity set by ≥ 5 points recall@10 without losing on the general set.

## Risks / Trade-offs

- [The labeller mislabels the inference form] → 39B reports labelling
  accuracy separately from check correctness; `unclassified` maps to
  `unverifiable`, never `valid`, so a mislabel cannot admit a bad inference.
- [Deterministic checks are too strict and reject sound prose] → the gate
  reports rejected sentences with their failing checks; 39B measures valid
  false rejection with a 0.15 ceiling; `no_surplus_content` uses normalised
  token match with a stop-list, tuned on the 39B development split only.
- [Four-way judge is worse than two-way on the original task] → 39A runs the
  original two-way metrics on the same 120 triples under both prompts; if
  four-way regresses unsupported recall below 0.90 the prompt is revised
  before the gate is offered in any profile.
- [The concept frame is just query rewriting] → 39C is designed to answer
  exactly this; if the frame does not clear its gate it stays as an optional
  diagnostic and the paper reports the null result.
- [Latency: one frame call plus one judge call per claim and per inference]
  → disclosed in the tool description; the `documents` profile is the only
  candidate for a default-on and only after 39A/39B; the `codebase` profile
  stays off.
- [`pipeline.py` refactor introduces a regression] → done first, on its own
  commit, with the existing answer test files as the oracle.
- [Julia 1 ONNX Python path is unverified] → a smoke task precedes 39A; if
  the export does not run under ONNX Runtime in Python, 39A keeps the NLI
  and seam cells and records the gap.

## Migration Plan

1. Land D7 (results extraction) with tests green.
2. Land `core/reasoning/` with settings default off and unit tests.
3. Land the judge builder and adapters behind the `judge` setting.
4. Run 39A, 39B, 39C; write the ADR.
5. Only then consider `documents.yaml` overrides.

Rollback: set both flags to `false` (the default). No data migration; no
stored artefacts change.

## Open Questions

- Which NLI cross-encoder to use in 39A (a DeBERTa-v3 NLI checkpoint is the
  default candidate). Deferrable: the adapter interface does not depend on
  the checkpoint.
- Whether the 40-question ambiguity set for 39C is drawn from the codebase
  corpus, the documents corpus, or both. Deferrable: it changes the
  experiment protocol, not the specs or tasks.
