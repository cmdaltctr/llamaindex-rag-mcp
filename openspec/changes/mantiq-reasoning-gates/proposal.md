# Proposal

## Why

The grounded answering path (ADR-057, ADR-059) proves that a cited claim is
entailed by its evidence. It does not check that the *question was understood*
before retrieval, and it does not check that a conclusion the model draws
*across* several supported claims is a valid inference. Experiment 20 closed
the judgement gap for single claims; the concept gap and the inference gap are
still open, and they are the two places where a model with correct evidence
still produces a wrong answer (wrong sense of a term, "may" promoted to
"always", "some" promoted to "all", affirming the consequent, "not A therefore
B" over a non-exhaustive list).

This change is Paper 2 of the fellowship programme. It adds opt-in gates
modelled on the classical Manṭiq distinction between conceptualisation
(Taṣawwur), judgement (Taṣdīq) and inference (Qiyās / Istidlāl). The mapping
is an engineering analogy, not a digitisation of the classical texts. It
builds on Paper 1 (`authority-aware-retrieval`), which labels evidence as
controlling, qualified, superseded or conflicting; those labels decide which
claims may serve as premises. The gates also work without Paper 1, over
unlabelled evidence.

Manṭiq is a plugin. It leaves the base answer pipeline unchanged. It uses the
ADR-080 mechanism that already exists: profile-owned pipeline graphs. A user
profile turns manṭiq on by using an Answer pipeline built from the new
`answer-mantiq` template. Built-in profiles never run it.

## What Changes

- New package `src/omrs/core/mantiq/`. All manṭiq code lives here:
  - `records.py`: frozen records `ConceptFrame`, `ClaimRecord`,
    `InferenceRecord`, `InferenceChecks`, serialisable without a model.
  - `params.py`: pydantic node parameters for the three operations.
  - `concept_frame.py`: builds a bounded `ConceptFrame` from the query (key
    terms, resolved meanings, canonical concept, broader / narrower / excluded
    concepts, universal-or-particular scope, divisions, operational definition
    and definition checks).
  - `tasdiq.py`: its own four-verdict judge prompt and parser (`supported`,
    `contradicted`, `unsupported`, `uncertain`, plus the conditions found in
    the evidence). It reuses the public `split_claims` from
    `core/answer/verify.py`. It does not change `verify.py`.
  - `inference.py`: finds inference sentences itself (cited or uncited) and
    labels each with a closed inference form and its premise structure.
  - `checks.py`: deterministic checks over the labels (fallacy patterns,
    exhaustiveness, modal strength, quantity, surplus content).
  - `gates.py`: the answer gate. It writes manṭiq's own `mantiq` result block.
  - `graph_adapters.py`: three graph operations, `mantiq.concept_frame`
    (query in, query out), `mantiq.tasdiq` (answer in, answer out) and
    `mantiq.qiyas` (answer in, answer out), each with a bypass, registered by
    one `register_mantiq_operations(catalogue)` line.
  - `templates.py`: the `answer-mantiq` graph and one named graph per
    experiment cell.
- One registration line in `build_operation_catalogue`
  (`src/omrs/compose_pipelines.py:59-70`). Registering an operation changes
  nothing until a graph uses it.
- The `answer-mantiq` template is published by `GET /v1/pipeline-templates`
  after the three canonical templates, which stay unchanged.
- The web workspace can load `answer-mantiq` into a user profile's Answer
  pipeline, and the chat shows the `mantiq` block.
- Three experiments (44A, 44B, 44C) and ADR-091 after the experiments.
- **No breaking change.** With no profile bound to a manṭiq template, the
  output of `Engine.answer`, of the graph path and of the MCP
  `answer_documents` tool is identical to v4 today. A golden test proves it.

## Capabilities

### New Capabilities

- `reasoning-gates`: opt-in manṭiq graph operations and template: a concept
  frame before retrieval, a four-verdict claim judgement with condition
  capture, inference-form validation over supported premises, and an answer
  gate that admits only validated content and reports the rest in its own
  result block.

### Modified Capabilities

None. The `grounded-answer-synthesis` requirements stay as they are: the
closed status schema, the meaning of `generation_unverified`, the ADR-059
two-way verdict set (`openspec/specs/grounded-answer-synthesis/spec.md:354-356`)
and the answer stage events. Manṭiq never reuses a base status or a base
verdict. The `pipeline-graphs` requirements already cover new operations and
non-canonical graphs, so they also stay as they are.

## Impact

- **Code**: new `src/omrs/core/mantiq/` (each file under 500 lines). One
  import and one call in `build_operation_catalogue`. `compose_pipelines.py`
  is at the 500-line ceiling, so `request_limit_issues` and its two helpers
  move to `compose_pipeline_runs.py` first, with no behaviour change.
  `compose_templates.py` gains `mantiq_templates()`. The templates route
  (`transports/api/routes/templates.py`) appends `answer-mantiq`. No change to
  `core/answer/`, settings models, `config/`, profile YAML, the Engine wiring,
  or the MCP and CLI handlers.
- **Settings / env**: none. Gate options are node parameters in a saved graph.
- **Dependencies**: none. The default judge is the existing `verify_llm`
  resource. Whether Experiment 44A adds NLI or small decision-model rows is
  decided later; any such model runs through Paper 1's adapter module.
- **Prerequisite from Paper 1**: `authority-aware-retrieval` owns the
  `authority_status` passthrough in `_evidence_rows`
  (`src/omrs/core/answer/evidence.py:28`). The gates read the field when it is
  present and behave normally when it is absent. This change does not edit
  `evidence.py`.
- **Import contracts**: a new contract forbids every base package from
  importing `omrs.core.mantiq`. `omrs.core.mantiq` joins the
  `core-business-avoids-providers-transports` source list and may not import
  `core.retrieval` or `core.ingestion`. No new ignore entries.
- **API**: `PipelineTemplate.name` gains `answer-mantiq`. `AnswerResponse`
  documents the optional `mantiq` block. The status enum, the verdict enum and
  the `AnswerStageEvent` stage enum stay unchanged.
- **Web**: one action in the Studio canvas and one block in the chat answer.
- **Tests**: golden output test first; new `tests/unit/test_mantiq_*.py` at
  the Core coverage tier (95 percent).
- **Experiments**: `experiments/44a-tasdiq-judge-comparison-<date>/`,
  `experiments/44b-inference-form-benchmark-<date>/`,
  `experiments/44c-concept-frame-ablation-<date>/`. Experiment 44C waits for
  Experiment 35A.
- **Docs**: `docs/guides/mantiq-reasoning-gates.md`, the operation table in
  `docs/guides/pipelines.md`, and `docs/adr/091-mantiq-reasoning-gates.md`.
