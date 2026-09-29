# Proposal

## Why

The grounded answering path (ADR-057, ADR-059) proves that a cited claim is
entailed by its evidence. It does not check that the *question was understood*
before retrieval, and it does not check that a conclusion the model draws
*across* several supported claims is a valid inference. Experiment 20 closed
the judgement gap for single claims; the concept gap and the inference gap are
still open, and they are the two places where a model with correct evidence
still produces a wrong answer (wrong sense of a term, "may" promoted to
"always", affirming the consequent, "not A therefore B" over a non-exhaustive
list).

This change is Paper 2 of the fellowship programme. It adds two opt-in gates
around the existing verification stage, modelled on the classical Manṭiq
distinction between conceptualisation (Taṣawwur), judgement (Taṣdīq) and
inference (Qiyās / Istidlāl). The mapping is an engineering analogy, not a
digitisation of the classical texts. It builds on Paper 1
(`authority-aware-retrieval`), which labels evidence as controlling, qualified,
superseded or conflicting; those labels become the premise set here. The gates
also work without Paper 1, over unlabelled evidence.

## What Changes

- New leaf package `core/reasoning/` with three pure-data-plus-logic modules
  and one settings model:
  - `concept_frame.py`: builds a bounded `ConceptFrame` from the query through
    the injected completion seam (key terms, resolved meanings, canonical
    concept, broader / narrower / excluded concepts, universal-or-particular
    scope, division categories for routing, operational definition, and
    definition-validation flags: inclusive, exclusive, non-circular).
  - `inference.py`: builds `InferenceRecord`s for any answer sentence that is
    not directly entailed by one evidence row. Each record names a closed
    inference form, its premise claim ids, a validity status, and the checks
    that ran (form validity, rejected fallacy patterns, exhaustiveness for
    disjunctive inference, modal-qualifier preservation, no-surplus-content).
  - `gates.py`: the answer gate. Only claims whose verdict is `supported` and
    inferences whose validity is `valid` reach the returned answer text.
    Rejected items are reported, never silently dropped.
  - `settings.py`: `ReasoningSettings` with `concept_frame_enabled` and
    `inference_gate_enabled`, both default `False`.
- The Taṣdīq gate **reuses** the ADR-059 verification stage. When the
  inference gate is enabled, the judge prompt is extended to return a
  four-way verdict (`supported`, `contradicted`, `unsupported`, `uncertain`)
  plus the modal conditions found in the evidence. With the gate disabled the
  existing two-way judge and its prompt are byte-identical.
- The concept frame, when enabled, is passed to retrieval as plain data
  (include / exclude terms, scope) and echoed in the answer result. It never
  imports retrieval code.
- Judge pluggability: the Taṣdīq verdict and the inference-form classification
  are closed-choice tasks. The completion seam stays the default judge; the
  design allows a local ONNX decision model (Julia 1) or a Natural Language
  Inference (NLI) cross-encoder to be injected through the same seam type.
  Choice is settled by Experiment 39A, not by this proposal.
- Three experiments (39A, 39B, 39C) and one ADR after the experiments.
- **No breaking change.** With both flags off the answer result, prompts and
  status schema are unchanged.

## Capabilities

### New Capabilities

- `reasoning-gates`: opt-in conceptualisation gate before retrieval, extended
  four-way claim judgement with condition capture, inference-form validation
  over supported premises, and an answer gate that lets only validated content
  through, with rejected content reported.

### Modified Capabilities

None. The existing `grounded-answer-synthesis` requirements (closed status
schema, referential citations, two-way verification off by default) are
preserved. The extended verdict set and the new result block only appear when
a reasoning flag is on, which is new behaviour, not a change to existing
behaviour.

## Impact

- **Code**: new `src/omrg/core/reasoning/` (four files, each under 500 lines).
  `core/answer/pipeline.py` is at 496 lines and gains two stage calls, so its
  error-result builders move to `core/answer/results.py` first. `AnswerSettings`
  gains a nested `reasoning: ReasoningSettings` block (`config/__init__.py` is
  at the 500-line ceiling and must not grow). `compose_answer.py` gains an
  optional judge builder for a decision model. `transports/mcp/answer.py` and
  the CLI answer command surface the new result block; no new tool.
- **Settings / env**: `ANSWER__REASONING__CONCEPT_FRAME_ENABLED`,
  `ANSWER__REASONING__INFERENCE_GATE_ENABLED`, `ANSWER__REASONING__JUDGE`
  (`seam` | `onnx_decision` | `nli`). Profile YAML may override them; the
  `documents` profile may enable them after Experiment 39.
- **Dependencies**: none in the base install. An ONNX decision model and an
  NLI cross-encoder are optional runtime downloads behind the `onnx_decision`
  and `nli` judge names, loaded lazily in `compose_answer.py`.
- **Dependency on Paper 1**: `authority-aware-retrieval` supplies
  `authority_status` on evidence rows. The inference gate reads it when
  present to reject premises marked `superseded` or `conflicting`; absent, all
  evidence rows are eligible premises.
- **Import contracts**: `omrg.core.reasoning` is added to the
  `core-business-avoids-providers-transports` source list. It imports only
  the standard library, pydantic and `core/settings`-style pure data. No new
  ignore entries.
- **Tests**: new `tests/test_reasoning_*.py` at the Core + MCP coverage tier
  (95 percent).
- **Experiments**: `experiments/39a-tasdiq-judge-comparison-<date>/`,
  `experiments/39b-inference-form-benchmark-<date>/`,
  `experiments/39c-concept-frame-ablation-<date>/`. Experiment 37 is claimed
  by `modular-ocr-workers-dots-mocr`; 38 is reserved for Paper 1.
- **Docs**: `docs/guides/reasoning-gates.md`, an update to
  `docs/guides/mcp-tools.md` for the new result block, and ADR-0xx once the
  experiments report.
