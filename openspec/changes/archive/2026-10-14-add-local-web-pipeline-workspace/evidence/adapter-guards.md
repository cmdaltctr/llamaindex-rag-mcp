# Graph adapter guards (task 3.8)

Date: 2026-10-13. Lead session, web worktree.

## Default-accessor leaf list

`tests/test_no_global_settings_reads.py` `_GUARDED_LEAVES` gains 14 modules:

- Retrieval: `operations.py`, `graph_adapters.py`, `graph_adapters_catalogue.py`, `graph_adapters_retrieve.py`, `graph_adapters_values.py`.
- Answer: `stages.py`, `results.py`, `graph_adapters.py`.
- Ingestion: `sources.py`, `commit.py`, `graph_adapters.py`, `graph_adapters_catalogue.py`, `graph_adapters_values.py`, `graph_fingerprint.py`.

`pipeline.py` and `replacement.py` stay off the list. Both still fall back to
`get_default_store` when a caller passes no store.

Result: `tests/test_no_global_settings_reads.py` 70 passed.

## Behavioural tests with poisoned defaults

Each domain has a test that installs raising process defaults and runs its adapters:

- `tests/unit/test_retrieval_graph_adapters.py::test_poisoned_process_defaults_are_never_read`
- `tests/unit/test_answer_graph_adapters.py::test_adapters_never_read_process_defaults`
- `tests/unit/test_ingestion_graph_adapters.py::test_adapters_never_read_process_defaults`

A poisoned default cannot detect an adapter that passes `store=None`: the
metadata layer then uses seed categories and reads no default. The new
`tests/unit/test_graph_adapters_store_forwarding.py` spies on the metadata
extractor and requires the run's own store object and the node's settings
object on every unit.

## Mutation checks (each restored and compared with `cmp`)

| Mutation | Test result |
|---|---|
| `prepare.enrich` passes `store=None` | before the new test: 27 passed (survived). After: forwarding test 1 failed |
| `prepare.enrich` passes a copy of settings | forwarding test 1 failed |
| `retrieve.*` reads `get_default_effective_settings()` | retrieval adapter tests 1 failed |
| `answer.*` reads `get_default_effective_settings()` for the judge | answer adapter tests 1 failed |

## Cross-domain import contracts

Three new import-linter contracts forbid direct sibling-domain imports from adapter modules:
`retrieval-graph-adapters-stay-in-domain`, `ingestion-graph-adapters-stay-in-domain`,
`answer-graph-adapters-stay-in-domain`.

| Check | Result |
|---|---|
| `lint-imports` on the real tree | 15 kept, 0 broken |
| retrieval adapter imports `..answer` | retrieval contract BROKEN |
| ingestion fingerprint imports `..retrieval` | ingestion contract BROKEN |
| answer adapter imports `..ingestion` | answer contract BROKEN |
| `tests/test_pipeline_import_boundaries.py`, `tests/test_contract_coverage.py` | 43 passed |
