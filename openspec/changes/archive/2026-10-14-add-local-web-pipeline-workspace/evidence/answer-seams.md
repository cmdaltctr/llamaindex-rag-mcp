# Answer seams (task 3.6, extraction part)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`.
Scope: extract the answer stages into seams that `Engine.answer` still uses.
Graph adapters are out of scope. `core/answer/` does not import `core.pipelines`.

Command prefix for every run below (v3 `.venv`, no installs):

    PATH=<v3>/.venv/bin:$PATH PYTHONPATH=src PDF_READER=pypdf \
      python -m pytest -q -p no:cacheprovider <files>

## Seams

`src/omrg/core/answer/stages.py` holds the steps. `src/omrg/core/answer/results.py`
holds the result shapes. `pipeline.answer()` now calls these functions. It keeps
only request limits, the master switch, the retrieval stage and MRTR timing.

| Seam | Purpose |
|---|---|
| `prepare_evidence(rows) -> list[dict]` | Number rows and keep lineage. Empty input gives empty evidence. |
| `await synthesise_answer(query, evidence, *, complete, answer_block, error_detail, runner=run_synthesis) -> SynthesisOutcome` | Run synthesis. Does not raise. Reports `failure_stage="generation"` and attempts made. |
| `resolve_citations(text, evidence, *, error_detail) -> CitationOutcome` | Map ordinals to supplied lineage. Absurd output becomes a generation failure. |
| `await verify_answer(text, evidence, *, grounded, answer_block, verify_complete, unavailable_reason, error_detail) -> VerificationFields` | Opt-in judge. Skips ungrounded answers. Does not raise. |
| `error_detail_for(settings)` / `safe_error_detail(exc, settings)` | Redact credentials from error text. |
| `results.no_evidence_result`, `no_provider_result`, `stage_failure_result`, `answered_result`, `disabled_result`, `answer_status`, `zero_generation_diagnostics`, `generation_diagnostics` | Build the public result dict. |

All seams take settings and seams as arguments. They do not read process defaults
and do not build a model (design D6).

## Test-first record

1. Baseline, existing answer suites before any change (`-m "not slow"`):
   `test_answer_citations_bounds`, `test_answer_compose`, `test_answer_core`,
   `test_answer_transport_cli`, `test_answer_transport_mcp`,
   `test_answer_transport_mrtr`, `test_answer_verify`,
   `test_synthesis_prompt_ceiling`, `test_engine`, `test_engine_isolation`,
   `test_openapi_conformance`, `test_no_global_settings_reads`,
   `test_file_size_ceiling`. Result: **243 passed**.
2. Golden capture. `tests/fixtures/pipeline_parity/answer/expected.json` was
   written by running the 18 cases in `cases.json` through the unchanged
   `answer()`. `git diff src/omrg/core/answer` was empty at capture time.
3. Parity before extraction: `tests/unit/test_answer_seams_parity.py`
   gave **20 passed**.
4. Seam tests red: `tests/unit/test_answer_seams.py` failed at collection with
   `ModuleNotFoundError: No module named 'omrg.core.answer.results'` (1 error).
5. Seams added, pipeline not yet rewired: both files **57 passed**.
6. Pipeline rewired to call the seams: both files **57 passed**.
7. Mutation checks (each change made, run, then restored from a backup):

   | Mutation | Result |
   |---|---|
   | Verification gate ignores `grounded` | 3 failed, 54 passed |
   | `verification_skipped` label dropped from the result | 8 failed, 49 passed |
   | Synthesis failure loses `failure_stage="generation"` | 6 failed, 51 passed |

8. After extraction, existing suites plus the two new files:
   **299 passed, 1 failed**. The failure is
   `tests/test_engine.py::test_public_api_exports_engine_effective_settings_version`.
   Another agent changed that test to expect new `Pipeline*` names in
   `omrg.__all__`. It does not touch answering.
9. `ruff check` and `ruff format`: clean. `lint-imports`: 8 kept, 0 broken.

## Parity fixtures

`cases.json` covers these behaviours. `answer()` and the chained seams must both
give the golden result. The comparison drops `*_ms` timings and keeps call counts.

| Area | Cases |
|---|---|
| No evidence (no model call) | `no_evidence_with_model`, `no_evidence_without_model` |
| Citations | `ok_single_citation`, `ok_merged_constituents`, `citation_dedupe_range_and_malformed`, `uncited_answer_is_unverified` |
| Failure attribution | `generation_failure_attributed`, `citation_assembly_failure_attributed_to_generation`, `no_provider_keeps_evidence`, `disabled_master_switch` |
| Verification | `verification_off_by_default_no_judge_call`, `verification_supported`, `verification_unsupported_claim`, `verification_all_unparseable_is_skipped`, `verification_no_judge_default_reason`, `verification_no_judge_transport_reason`, `verification_judge_failure_degrades`, `verification_skipped_for_uncited_answer` |

Other tests in `tests/unit/test_answer_seams.py`:

- `test_seam_citations_resolve_to_stored_chunks` ingests a document and builds
  citations with the seams. Each cited `chunk_id` must refetch exactly one stored
  chunk. The result must also match `answer()` for the same rows.
- `test_retrieval_failure_is_attributed_before_any_model_call` checks that a store
  failure gives `failure_stage="retrieval"` with no model call.
- `test_seams_never_read_process_default_settings` makes the default-settings
  accessor raise. It then runs the full seam chain.
- `test_answer_seam_modules_stay_lazy_and_graph_free` imports the seam modules in
  a new process. It checks that `compose_answer`, `core.pipelines`, `transports`
  and `integrations` stay unloaded.

## Kept contracts

- Patch target `omrg.core.answer.pipeline.run_synthesis` still works. The pipeline
  passes `runner=run_synthesis` when it runs. The MRTR exhaustion test passes.
- `pipeline.disabled_result`, `ResolvedRetrieval`, `evidence_rows`,
  `labelled_nodes` and `_QUERY_MAX_CHARS`/`_TOP_K_MAX`/`_EXPAND_WINDOW_MAX` are
  still importable from `pipeline`.
- File sizes: `pipeline.py` went from 496 to 352 lines. `stages.py` has 257 lines
  and `results.py` has 227.

## Not done here

- Graph adapters for the Answer / verify family.
- `stages.py` and `results.py` are not yet in `_GUARDED_LEAVES`. That list belongs
  to task 3.8 and is not in this agent's files. Both modules pass the poisoned
  default test above.

## Graph adapters (task 3.6, adapter part)

Date: 2026-10-13. Same branch and command prefix, with the worktree
`.venv` (`PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest`).

### Files

| File | Lines | Purpose |
|---|---|---|
| `src/omrg/core/answer/graph_adapters.py` | 420 | Four async adapters, four descriptors, `register_answer_operations`. |
| `tests/unit/test_answer_graph_adapters_support.py` | 184 | Fakes and a hand-run chain. No tests. |
| `tests/unit/test_answer_graph_adapters_parity.py` | 67 | The 18 parity cases through the chain. |
| `tests/unit/test_answer_graph_adapters.py` | 423 | Descriptor, wiring, laziness, attribution and verification tests. |

No existing `core/answer` module changed.

### Operations

| Operation | Effect | Inputs | Output | Parameters |
|---|---|---|---|---|
| `answer.prepare_evidence` v1 | `pure` | `context` (context, chunk lineage) | `context` (context, chunk lineage) | none |
| `answer.synthesise` v1 | `model_call` | `query` (query), `context` (context, chunk lineage) | `answer` (answer, no lineage) | `include_diagnostics: bool = False` |
| `answer.cite` v1 | `pure` | `answer` (answer) | `answer` (answer, chunk lineage) | none |
| `verify.claims` v1 | `model_call` | `answer` (answer, chunk lineage) | `answer` (answer, chunk lineage) | `verify_claims: bool or None` (lever `answer.verify_claims`) |

- `verify.claims` declares a bypass (`answer` to `answer`).
- The `answer` port of `answer.synthesise` has no chunk-lineage guarantee.
  Thus validation rejects `synthesise -> verify` with `incompatible_ports`.
  Citations must resolve before verification.
- No operation has a prompt-like string parameter, so `free_text_params` is
  empty. The standard path has no such parameter, and adding one would break
  parity.
- No operation declares a capability. A host with no answer model gets the
  existing no-provider result, as `Engine.answer` gives.

### Value carried between nodes

Every `answer` port value is the public result dict. The builders in
`results.py` make each one. A graph output therefore has the same shape as
`Engine.answer`.

1. `answer.synthesise` checks the master switch, numbers the context, and
   returns `no_evidence_result` for empty context. Only then does it resolve
   `answer_llm`. Text that is not cited yet has status
   `generation_unverified`, which is its true guarantee at that point.
2. `answer.cite` acts only on a result with answer text and no verification
   label. A bad citation gives `failure_stage="generation"` with the evidence
   kept.
3. `verify.claims` acts only on status `ok` (grounded) with
   `answer.verify_claims` on. Then it resolves `verify_llm`. A missing or
   failing judge gives `verification_skipped` with the reason. The reason is
   also put in `NodeOutput.fallback`.
4. All other values go through unchanged: no evidence, no provider, switch
   off, a failed stage, or an answer that has a verification label.

`retrieval_ms` is `0.0` in diagnostics. Retrieval runs in earlier nodes.

### Resource contract (for the composition agent)

| Name | Value | When the adapter reads it |
|---|---|---|
| `answer_llm` | Callable with no arguments. Returns an LLM with `async acomplete(prompt)` (result has `.text`), an async `prompt -> str` seam, or `None`. | After the switch check and after evidence is not empty. Missing or `None` gives the no-provider result. An exception from the callable fails the node, as `Engine.answer` raises. |
| `verify_llm` | Callable that takes `settings.answer`. Returns the same kinds of value. | Only for a grounded answer with `verify_claims` on. An exception gives `verification provider unavailable: <Type>: <redacted detail>`. `None` gives the no-judge reason. |

The callables must memoise the model, as `Engine` does with `_answer_llm`.
`NodeContext` copies its resource mapping, so a lazy mapping does not work.
A callable is necessary to keep the models unbuilt until use.

### Test-first record

1. Tests written first. Both new test files failed at collection:
   `ModuleNotFoundError: No module named 'omrg.core.answer.graph_adapters'`
   (2 errors).
2. Module added: **40 passed**. The preflight wiring test was added after
   this. It gave **41 passed**.
3. Mutation checks (each change made, run, then restored from a scratch
   copy and checked with `cmp`):

   | Mutation | Result |
   |---|---|
   | Resolve `answer_llm` before the no-evidence check | 2 failed, 38 passed |
   | Verification ignores `grounded` (always `True`) | 2 failed, 38 passed |
   | Judge factory failure reason dropped | 2 failed, 38 passed |
   | Verification fallback not reported | 2 failed, 38 passed |
   | Citation failure loses `failure_stage` | 2 failed, 38 passed |
   | Synthesis reads `get_default_effective_settings()` | 2 failed, 38 passed (poisoned-default test and accessor scan) |
   | `verify.claims` accepts an uncited answer port | 2 failed, 20 passed (port contract and preflight tests) |

4. Regression run (`-m "not slow"`): new files, `test_answer_seams*`, all
   `tests/test_answer_*.py`, `test_synthesis_prompt_ceiling`,
   `test_no_global_settings_reads`, `test_file_size_ceiling`,
   `test_pipeline_import_boundaries`, `test_pipeline_catalogue`,
   `test_pipeline_guide`, `test_engine`. Result: **364 passed, 1 deselected**.
5. `ruff check` and `ruff format --check`: clean. `lint-imports`: 12 kept,
   0 broken.

### Parity

All 18 cases in `cases.json` run through
`prepare -> synthesise -> cite -> verify` and equal `expected.json`. The
comparison drops `*_ms` timings and keeps key order and model and judge
call counts.

One case needs a translation. `verification_no_judge_transport_reason`
gives `answer()` a reason string from the transport. A graph host reports
the same problem as a `verify_llm` callable that raises. For this case the
test runs `answer()` with the reason `Engine.answer` builds from that
exception, and compares the two results.

### Other checks

- Empty context: no resource lookup and no model call. This is also true
  with no resources at all.
- The answer model is resolved once. The judge is never resolved when
  verification is off, when the answer is not cited, or after a generation
  failure.
- The judge reason removes `openrouter_api_key` from the error text.
- Poisoned `get_default_effective_settings`, `resolve_effective_settings`
  and `get_default_store`: the chain still gives the golden result.
- The adapter module passes the default-accessor scan in
  `tests/test_no_global_settings_reads.py`.
- A fresh import of the adapter module loads no ingestion, retrieval,
  provider, composition, transport or integration module.

### Not done here

- `core/answer/graph_adapters.py` is not yet in `_GUARDED_LEAVES` (task 3.8).
- The composition root does not call `register_answer_operations` yet, and
  `Engine` does not supply `answer_llm` or `verify_llm`. That is a later task.
- Graph answers do not apply the `answer()` request limits (query length,
  `top_k`, `expand_window`). Those belong to the retrieval nodes and to the
  run inputs.
