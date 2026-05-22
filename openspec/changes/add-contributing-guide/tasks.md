## 1. CONTRIBUTING.md

- [x] 1.1 Create `CONTRIBUTING.md` at the repo root
- [x] 1.2 Add Welcome section pointing at `AGENTS.md` for AI agents
- [x] 1.3 Add Setup section that links to `docs/guides/getting-started.md` (no duplicated install commands)
- [x] 1.4 Add "The Contribution Loop" section with a Mermaid `flowchart TD` covering: setup → branch → trivial-fix decision → OpenSpec proposal → implementation → experiment decision → tests → coverage gate → architectural decision → ADR → conventional commit → PR → archive
- [x] 1.5 In the diagram, spell `Implement` out fully (not `Imp`) on the node label and node id
- [x] 1.6 Add "Step by step" prose section with one short subsection per node, each linking to the deeper doc
- [x] 1.7 Add Coding Conventions section linking to `AGENTS.md` (no duplicated conventions)
- [x] 1.8 Add Commit and PR Conventions section with the Conventional Commits → PSR table (taken from `AGENTS.md` release automation)
- [x] 1.9 Add PR Checklist section
- [x] 1.10 Add "Where to Find Things" reference table covering setup, conventions, ADRs, OpenSpec, experiments, tests, configuration, CLI reference, MCP tool reference, architecture
- [x] 1.11 Add Licence note (MIT)

## 2. tests/TEST_README.md

- [x] 2.1 Create `tests/TEST_README.md`
- [x] 2.2 Add Quick Start section with the four canonical commands (fast suite, coverage, slow E2E, single test/test-by-name)
- [x] 2.3 Add Coverage Floors table mirroring the `AGENTS.md` table; cross-link to `docs/guides/testing.md` for rationale
- [x] 2.4 Add Test Files inventory table mirroring `docs/guides/testing.md` and including `test_async_ingest_responsiveness.py`
- [x] 2.5 Add "What conftest.py does for you" section covering the three autouse fixtures (ChromaDB EphemeralClient, MockEmbedding, module-level constants via sys.modules)
- [x] 2.6 Add Gotchas section: reranker singleton reset, EphemeralClient state leak, `METADATA_EXTRACTION_MODE` module-level patching, `@pytest.mark.slow` exclusion, `connected_client` is a context manager not a fixture, MCP tool handlers never raise, backward-compat for tool params, `÷30` reranker threshold note
- [x] 2.7 Add "Adding a new test" section: where to put it, class-based pattern, async marker note, fixtures under `tests/fixtures/`, slow marker rule, coverage check
- [x] 2.8 Add "When tests fail" troubleshooting section
- [x] 2.9 Add "See also" links to `docs/guides/testing.md`, `AGENTS.md`, `CONTRIBUTING.md`, `pyproject.toml`

## 3. README.md

- [x] 3.1 Add a "Contributing" row to the documentation table in `README.md` pointing at `CONTRIBUTING.md`

## 4. Validate

- [x] 4.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm 332 tests pass and coverage floors hold (pure docs change — no regressions expected)
- [x] 4.2 Run `openspec validate add-contributing-guide` and confirm the change is valid
- [x] 4.3 Spot-check rendered Mermaid in `CONTRIBUTING.md` via GitHub preview after push
- [ ] 4.4 Open PR via `gh pr create` (deferred to PR step)

## 5. ADR Decision

- [x] 5.1 Decide whether an ADR is warranted. Decision: **no** — ADRs in this repo record architectural tradeoffs (uv vs poetry, ChromaDB vs alternatives, async vs sync ingest, cross-encoder reranker). "Add a contributing guide" has no architectural tradeoff. Rejected alternatives are recorded in `design.md` instead, which is the right level of formality. Rationale captured inline in `proposal.md` Impact section.

## 6. Archive

- [ ] 6.1 After PR merge, archive via `openspec-archive-change` skill (user does this manually per project convention).
