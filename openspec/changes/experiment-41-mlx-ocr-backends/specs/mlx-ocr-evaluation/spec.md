# Spec Delta

## Purpose

Define how OMRG evaluates an MLX backend for an OCR engine against the engine's shipped backend, so that a decision to add an MLX engine rests on a fair and complete comparison.

## ADDED Requirements

### Requirement: The evaluation SHALL compare each MLX arm with its own baseline on the same pages

Each MLX arm SHALL run the same page list as its baseline arm, with the same prompt, render size, token cap, decoding rule and post-processing.

#### Scenario: Baseline results come from an earlier experiment
- **WHEN** a baseline arm reuses results from an earlier experiment
- **THEN** the page list SHALL be copied from that experiment and frozen with a SHA-256
- **AND** the report SHALL name the source files of the baseline

#### Scenario: The MLX arm uses a different page list
- **WHEN** the page list of an MLX arm differs from its baseline
- **THEN** the comparison SHALL NOT count toward any gate

### Requirement: Timings SHALL be measured on an otherwise idle machine

An MLX arm SHALL run alone, one arm at a time, with no other GPU job.

#### Scenario: Another GPU job runs during an MLX arm
- **WHEN** another GPU job runs while an MLX arm is timed
- **THEN** the timings of that arm SHALL be marked as measured under shared load
- **AND** the arm SHALL NOT count toward the speed gate until it is re-run

#### Scenario: The baseline ran under shared load
- **WHEN** the baseline timings came from a run with shared load
- **THEN** the report SHALL state this limit beside every speed comparison
- **AND** the plan SHALL record whether the operator ordered a baseline re-timing control

### Requirement: Memory SHALL include every process of the backend

Peak memory for an MLX arm SHALL be the sum of the peak physical footprint of the client process and the server process.

#### Scenario: The backend uses a separate server
- **WHEN** an arm calls a local inference server
- **THEN** the reported peak memory SHALL include the server process
- **AND** the report SHALL name the sampling method

### Requirement: Output quality SHALL be measured against the baseline and the references

The evaluation SHALL report the KaTeX 0.16.22 render error rate, token recall on the script and handwriting pages, the operator's verdict on invented text, and the per-page token similarity to the baseline arm.

#### Scenario: A formula differs from the baseline
- **WHEN** a formula in the baseline output is altered or missing in the MLX output
- **THEN** the report SHALL list it
- **AND** the list SHALL appear even when every gate passes

#### Scenario: A page returns no text
- **WHEN** a page times out or returns empty text
- **THEN** the page SHALL count as scored 0.0 in the recall view that includes all pages
- **AND** the report SHALL also give the view over pages with output

### Requirement: The operator SHALL set the gates before any run

The protocol MAY propose candidate gates. The operator SHALL set or replace them in the plan, and the plan SHALL be frozen before the first run.

#### Scenario: No gate is set
- **WHEN** the plan shows the gates as not set
- **THEN** no OCR run SHALL start

#### Scenario: A gate changes after a run starts
- **WHEN** the operator changes a gate after an MLX arm has started
- **THEN** the change SHALL be recorded as a dated amendment with its reason
- **AND** the report SHALL show the original rule

### Requirement: Installs, downloads, the licence check and runs SHALL need the operator's approval

The plan SHALL hold one approval for installing the MLX runtime, one for downloading model weights, one for the licence check of each converted model, and one for the OCR run budget. Each approval SHALL stay false until the operator sets it.

#### Scenario: An approval is false
- **WHEN** an approval in the plan is false
- **THEN** the work it covers SHALL NOT start
- **AND** no other approval SHALL imply it

#### Scenario: A converted model derives from a model with extra licence terms
- **WHEN** a converted model derives from a model whose agreement covers derivative works
- **THEN** the operator SHALL decide, before download, whether the earlier acceptance covers the conversion
- **AND** the decision SHALL be recorded in the plan

### Requirement: The evaluation SHALL NOT change shipped behaviour

The evaluation SHALL NOT change any engine folder, route, setting default or dependency of OMRG.

#### Scenario: An MLX arm passes its gates
- **WHEN** an MLX arm passes
- **THEN** the report SHALL name a follow-up OpenSpec change as the next step
- **AND** no engine, route or default SHALL change in this change

#### Scenario: Only one arm passes
- **WHEN** one engine's MLX arm passes and the other fails
- **THEN** the follow-up SHALL cover only the engine that passed
- **AND** the other engine SHALL stay on its current backend
