# Design

## Context

See proposal.md, "Why". The relevant current state, checked against v4 HEAD:

- The direct answer path is `core/answer/pipeline.py` (358 lines). It runs
  retrieve, synthesise, cite, optional verification (ADR-059) and the status
  decision. The result builders already live in `core/answer/results.py`
  (`base_result`, `zero_generation_diagnostics` and the failure builders).
  Built-in profiles answer through this path.
- Verification is `core/answer/verify.py` (477 lines): a two-way judge
  (`supported` / `unsupported`, plus `unparseable`) over the
  `(claim, ordinals)` pairs from `split_claims()` (`verify.py:173`).
- ADR-080 profile-owned graphs: `build_operation_catalogue()`
  (`src/omrg/compose_pipelines.py:59-70`) registers each domain's operations.
  A user profile names its answer graph through `answer_pipeline_id`
  (`src/omrg/core/workspace/records.py:71`). `engine_profiles.answer()`
  returns the graph's `answer` output unchanged (`engine_profiles.py:269-273`).
  User-profile collections answer only through their graph with the server
  model (`transports/mcp/answer.py:196-199`, design D17 of that change).
- The answer graph operations (`core/answer/graph_adapters.py`) pass the
  public answer dict from node to node. `verify.claims`
  (`graph_adapters.py:313-352` and `401-416`) is the model for an opt-in
  answer-in, answer-out step: a `BypassSpec`, resources looked up only when
  needed, and a missing judge reported as a skip with a reason.
- Resources reach adapters only through `NodeContext.resource()`
  (`core/pipelines/adapters.py:94`). The Engine supplies `answer_llm` and
  `verify_llm` (`engine_lifecycle.py:105-115`). The `verify_llm` factory
  returns `None` unless the answer block has `verify_claims` on
  (`compose_answer.py:216`).
- Templates: `pipeline_templates.py` publishes exactly three canonical
  templates (`TEMPLATE_NAMES`, line 39). `compose_templates.profile_templates`
  maps each canonical template to a profile slot, and the OpenAPI
  `PipelineTemplate.name` enum lists the three names (`openapi.yaml:7160`).
  The Studio gallery shows no template section and never calls
  `GET /v1/pipeline-templates` (`web/src/studio/StudioView.test.tsx:54-63`).
  The canvas palette lists every catalogue operation from
  `GET /v1/pipeline-operations`.
- Size limits that bind this design: `compose_pipelines.py` is at 500 lines;
  `config/__init__.py` is 470 lines and is not touched.
- Experiment 20 measured the two-way judge: GLM-5.3 reached recall 1.0 and
  false rejection 0.0 on 120 frozen triples (60 supported, 60 unsupported).
- Paper 1 (`authority-aware-retrieval`) owns the `authority_status`
  passthrough in `_evidence_rows` (`core/answer/evidence.py:28`). It copies
  the field only when a row has it and leaves `_EVIDENCE_FIELDS` unchanged.

## Goals / Non-Goals

**Goals:**

- Ship manṭiq as an opt-in plugin: graph operations plus a template.
- Keep the base answer output byte-identical when no profile binds a manṭiq
  template, proved by a golden test recorded before any code.
- Keep every manṭiq record a frozen dataclass, so results are serialisable
  and testable without a model.
- Make each experiment cell a named template, so the paper's runs are
  reproducible.

**Non-Goals:**

- Any change to `core/answer/`, settings models, `config/`, profile YAML,
  Engine wiring, or the MCP and CLI handlers.
- Running manṭiq in the built-in `documents` or `codebase` profiles.
- Formal syllogistic figures and moods. The closed `inference_type` set is a
  pattern vocabulary for a validator, not a logic engine.
- A new MCP tool or a new answer status.
- Changing retrieval. The concept frame only rewrites the query text.
- Training or fine-tuning any model.

## Decisions

### D1. One package: `core/mantiq/`

All manṭiq code lives in `src/omrg/core/mantiq/`: `records.py`, `params.py`,
`concept_frame.py`, `tasdiq.py`, `inference.py`, `checks.py`, `gates.py`,
`graph_adapters.py` and `templates.py`. It may import `core.answer` public
helpers and `core.pipelines`. It may not import `core.retrieval`,
`core.ingestion`, a provider or a transport. No base package imports it: a new
import-linter contract (`base-never-imports-mantiq`) enforces that, in the
style of the existing contracts (`unmatched_ignore_imports_alerting =
"error"`). The only importers are composition modules: `compose_pipelines.py`
(the registration line) and `compose_templates.py` (the template).
Alternative considered: a sibling `core/reasoning/` wired into
`core/answer/pipeline.py`. Rejected: it changes the base path.

### D2. Manṭiq is graph operations plus a template, and nothing else

`graph_adapters.py` registers three operations through one
`register_mantiq_operations(catalogue)` call in `build_operation_catalogue`:

| Operation | Ports | Resource | Bypass |
|---|---|---|---|
| `mantiq.concept_frame` | query in, query out | `answer_llm` | query to query |
| `mantiq.tasdiq` | answer in, answer out | `verify_llm` | answer to answer |
| `mantiq.qiyas` | answer in, answer out | `verify_llm` | answer to answer |

Each operation follows `verify.claims`: it passes the value through unchanged
when there is no answer text, it looks up a resource only when it needs one,
and a missing resource is a skip with a reason, never an exception. A
registered operation changes nothing until a saved graph uses it. Users turn
manṭiq on by giving a user profile an Answer pipeline built from the
`answer-mantiq` template (D9). Built-in profiles use the direct path and never
run a manṭiq node.

Gate options are pydantic node parameters in `params.py`
(`extra="forbid"`, frozen): `ConceptFrameParams.augment_query: bool = True`,
`TasdiqParams` with no fields, and `QiyasParams.filter_answer: bool = True`.
The node's enabled flag is the on/off switch. There is no settings block, no
env key and no lever. Alternative considered: a nested `answer.reasoning`
settings block read by `pipeline.py`. Rejected: it edits the base settings,
the base pipeline and every transport.

### D3. Taṣdīq has its own four-verdict judge

`tasdiq.py` holds its own prompt and parser. It reuses the public
`split_claims()` to get `(claim, ordinals)` pairs and the cited evidence
texts. The prompt treats evidence as quoted data with delimiters and an
instruction hierarchy, the same injection rule ADR-059 applies. The reply
gives one verdict from `supported`, `contradicted`, `unsupported`,
`uncertain`, and a `conditions:` line (at most 8 qualifiers such as `may`,
`if`, `unless`, `only when`). A reply that does not parse gives the verdict
`unparseable` inside the `mantiq` block. `verify.py`, `stages.py`, the
ADR-059 verdict set, the OpenAPI verdict enum (`openapi.yaml:5168`) and the
meaning of `generation_unverified` stay unchanged. In the `answer-mantiq`
template the `verify.claims` node is kept but disabled (bypassed), so the
judge reads each claim once. Alternative considered: a `verdict_mode` keyword
on `verify_claims()`. Rejected: it edits the base judge.

### D4. The inference gate is a validator over records; the model only labels

`inference.py` finds inference sentences itself. A sentence is a candidate
when it carries an inference marker (`therefore`, `so`, `thus`, `hence`,
`it follows`, `consequently`) or cites two or more evidence rows. This also
catches an uncited "therefore" sentence, which `split_claims()` skips by
design. The model, through the judge, does two closed-choice jobs per
candidate: label the `inference_type` and extract the premise structure
(antecedent / consequent, disjuncts, quantity words, modal markers). Every
check then runs in Python in `checks.py`:

- `premises_supported`: every `premise_claim_id` has verdict `supported`.
- `form_valid`: the labelled type is in the closed set and its slots are
  filled.
- `no_affirmed_consequent` and `no_denied_antecedent`: pattern match on the
  labelled conditional and the part the second premise affirms or denies.
- `alternatives_exhaustive`: true only if the disjunctive premise's evidence
  holds an exhaustiveness marker (`only`, `exactly one of`, `either … or …
  and no other`) or the frame marks the division exhaustive. Absent both, the
  inference is `unverifiable`, never `valid`.
- `qualifiers_preserved`: on the fixed scale `may` < `can` < `should` <
  `must` = `always`, the conclusion may not be stronger than the weakest
  premise condition.
- `quantity_preserved`: for categorical chaining, the conclusion's quantity
  (`some` < `all`) may not exceed the weakest premise, and two particular
  premises give no conclusion.
- `no_surplus_content`: entities, numbers and conditions in the conclusion
  must appear in a premise text (normalised token match with a stop-list).

Rationale: the reviewer objection to an LLM-run logic gate is that the model
grades its own homework. Deterministic checks keep the gate auditable and
give Experiment 44B a clean split between labelling accuracy and check
correctness.

### D5. The concept frame is a bounded schema that only rewrites the query

`ConceptFrame` has fixed fields and caps (12 items per list, 512 characters
per string). The model returns a fenced JSON block; a parse failure or a
missing model gives a skip with a reason, and the query passes unchanged.
With `augment_query` on, the node appends the canonical concept and narrower
concepts to the query text it emits. Exclude terms and scope are recorded,
not applied, because retrieval takes no new parameter in this change. The
answer result has no generic annotations port, so the frame is recorded in
the node summary of the run. Bounded caps keep the summary small; the run
record truncates a larger preview with an artefact reference.

### D6. Premise eligibility reads `authority_status` as an optional field

`gates.py` builds the premise set from `ClaimRecord`s. When all cited rows of
a claim carry `authority_status` `superseded` or `conflicting`, the claim
becomes `uncertain` with a named reason. When no row carries the field, every
`supported` claim is a premise. This is a dict lookup with a default. Paper 1
owns the passthrough in `evidence.py`; this change does not edit it.

### D7. The judge is the existing `verify_llm` resource

`mantiq.tasdiq` and `mantiq.qiyas` call `context.resource("verify_llm")`
with a copy of the node's answer block that has `verify_claims` set to true.
The copy is needed because the factory returns no judge when that flag is off
(`compose_answer.py:216`). A missing resource, a `None` judge or a raising
factory gives a skip with the redacted reason. `mantiq.concept_frame` uses
`answer_llm`. Natural Language Inference (NLI) cross-encoders and small
decision models such as Julia 1 are not labellers: they pick one label from a
list, so they cannot extract conditions or premise structure. Whether any of
them appears in Experiment 44A, and in what role, is decided later
(Open Questions). Experiment 38 found Julia 1 weaker than Clef-flash. Any such
model runs through Paper 1's adapter module (`integrations/authority_models.py`,
authority-aware-retrieval task 9.3), not a second copy.

### D8. The answer gate writes its own `mantiq` block

`mantiq.tasdiq` adds `mantiq.claims`. `mantiq.qiyas` adds
`mantiq.inferences`, `mantiq.rejected` (text, reason, failing checks) and
`mantiq.outcome` (`all_admitted`, `some_rejected`, `nothing_admitted` or
`skipped` with `mantiq.skipped_reason`). With `filter_answer` on and at least
one admitted sentence, `answer` holds only supported claims and valid
conclusions, and `mantiq.original_answer` holds the text before the gate.
When nothing is admitted, `answer` stays as written and the outcome is
`nothing_admitted`, because the base `status` describes that text and an
empty answer under `status="ok"` would mislead. `status`, `citations`,
`evidence`, `verified`, `unverified_claims` and `verification_skipped` are
never changed by a manṭiq node.

### D9. One published template; experiment cells as named graphs

`templates.py` is a pure transform over a base answer graph document. It
inserts `mantiq.concept_frame` between the graph's `query` input and
`retrieve.prepare_query` (the synthesise step keeps the original question),
disables `verify.claims`, and appends `mantiq.tasdiq` then `mantiq.qiyas`
before the `answer` output. It also holds a table of named cells for the
experiments (for example frame only, Taṣdīq only, full chain).
`compose_templates.mantiq_templates(engine)` applies the transform to the
canonical answer template shaped for the Engine. `GET /v1/pipeline-templates`
appends only `answer-mantiq` after the three canonical templates, which stay
byte-identical; `canonical_templates()` and `TEMPLATE_NAMES` stay unchanged,
because `profile_templates()` maps each canonical name to a slot. The web
canvas offers "Use the manṭiq answer template" on a user profile's Answer
pipeline. It fetches the template only when the user picks the action, so the
gallery still makes no template call.

### D10. Experiment numbering and gates

Experiments 36 to 39, 41 and 42 are taken; 43 belongs to Paper 1. This change
claims 44A, 44B and 44C. Every cell is a named template from D9.

- **44A Taṣdīq judge comparison.** Inputs: the 120 Experiment 20 triples,
  relabelled into four verdicts, plus 60 new triples with modal qualifiers.
  The relabel uses the attack classes (contradicted to `contradicted`,
  invented and swapped to `unsupported`, faithful and paraphrase to
  `supported`), then a human pass, then a blind second-annotator check on a
  stratified 40-triple sample, all before any judge run. This matches the
  40-pair spot check Paper 1 uses. Cells: the seam judge with the four-verdict
  prompt (primary), the ADR-059 two-way judge on the same triples, and the
  lexical baseline. Extra model rows (NLI cross-encoder, a small decision
  model) are decided later, from Paper 1's model choice (its task 9.1) and
  smoke test (its task 9.2). Metrics: four-way macro-F1, unsupported recall, false
  rejection, conditions exact match, P95 latency, cost per claim. Gate:
  unsupported recall ≥ 0.90 and false rejection ≤ 0.10 on the 120 triples.
- **44B Inference-form benchmark.** 150 to 200 items built from retrieved
  premises over the quality corpus and the Paper 1 authority corpus: per form,
  valid instances, the matching fallacy, a non-exhaustive disjunction, a
  strengthened qualifier, a strengthened quantity, and a surplus-content
  conclusion. Gold labels are written and checked by a blind second annotator
  on 40 items before any gate run. Metrics: labelling accuracy per form, check
  precision and recall, invalid-inference rejection rate, valid-inference
  false rejection. Gate: invalid rejection ≥ 0.85 with valid false rejection
  ≤ 0.15.
- **44C Concept-frame ablation.** Starts only after Experiment 35A has run
  (the open change `experiment-35-full-document-rag-benchmark`). Cells: raw
  query, multi-query rewrite, HyDE-style hypothetical passage, concept frame.
  Metrics: recall@10 and nDCG@10 on the 35A document subset plus a
  40-question ambiguity set. Gate for keeping the frame as a first-class
  stage: beat the best rewrite baseline on the ambiguity set by ≥ 5 points
  recall@10 without losing on the general set.

## Risks / Trade-offs

- [A manṭiq change leaks into the base output] → the golden test is recorded
  on v4 HEAD before any code and rerun at the end; the new import contract
  stops a base import of `core.mantiq`.
- [The labeller mislabels the inference form] → 44B reports labelling
  accuracy apart from check correctness; `unclassified` maps to
  `unverifiable`, never `valid`.
- [Deterministic checks reject sound prose] → rejected sentences are listed
  with their failing checks; 44B caps valid false rejection at 0.15; the
  stop-list is tuned on the 44B development split only.
- [The four-verdict prompt is worse than two-way on the original task] → 44A
  scores both prompts on the same 120 triples; below 0.90 unsupported recall,
  the prompt is revised before ADR-091 recommends the template.
- [The concept frame is just query rewriting] → 44C answers this; a null
  result keeps the frame as an optional node and the paper reports it.
- [Latency: one frame call, one judge call per claim and per inference] →
  each node summary records its call count and time; only users who bind the
  template pay the cost.
- [`compose_pipelines.py` move introduces a regression] → done first, on its
  own commit, with the existing pipeline tests as the oracle.

## Known limits

- The answer result has no generic annotations port, so the concept frame is
  recorded only in the node summary of the run.
- Chat answers through a profile graph make no run record
  (`engine_profiles.py:8-9`). The `mantiq` block still reaches chat, because
  the graph's answer result passes straight through. The concept frame is
  visible only in Studio runs.
- `request_limit_issues` treats any graph with an enabled node that outputs an
  `answer` port as an answering graph (`compose_pipelines.py:232-243`). The
  `answer-mantiq` template therefore gets the same request limits as a plain
  answer graph. Manṭiq node parameters add no new limit.
- The MCP client-sampling path runs retrieval itself
  (`transports/mcp/answer_mrtr.py:178-207`, `_retrieve` calls
  `engine.search`). It serves built-in profiles only, so the concept frame
  cannot steer retrieval there. This is out of scope.
- Built-in profiles cannot run manṭiq.
- Graph runs report answer stages from the shared base steps
  (`engine_profiles.py:230-237`). Manṭiq nodes report no stage, so the
  `AnswerStageEvent` enum (`openapi.yaml:6973`) stays unchanged; the frame
  runs under `searching` and the gates run after the last base stage.

## Migration Plan

1. Record the golden output on v4 HEAD.
2. Make room in `compose_pipelines.py` with no behaviour change.
3. Land `core/mantiq/` with unit tests and the import contracts.
4. Register the operations, publish the template, add the web action.
5. Rerun the golden test; run 44A, 44B and 44C; write ADR-091.

Rollback: remove the registration line and the template entry. No setting,
stored vector or record schema changes. Saved graphs that use a manṭiq
operation fail validation with an unknown-operation issue.

## Open Questions

- Whether Experiment 44A includes NLI or small decision-model rows, and
  which checkpoints. Deferred by the user on 22 October 2026. Experiment 38
  found Julia 1 weaker than Clef-flash. Decide with Paper 1's task 9.1.
- Whether the 44C ambiguity set comes from the codebase corpus, the
  documents corpus or both. Deferrable: it changes the protocol only.
- Deferred, optional: a generic hook in `engine_lifecycle.py` to register an
  extra graph resource (for example a local decision model as a judge). Not
  needed now, because the default judge is `verify_llm`.
