## Why

The repository has rich process documentation — `AGENTS.md` for conventions,
`docs/adr/ADR_README.md` for architectural decisions, `experiments/EXP_README.md`
for empirical evaluations, `docs/guides/testing.md` for the test suite, and
`docs/guides/getting-started.md` for setup — but no single entry point that
shows a new contributor how those pieces fit together. Someone landing on the
repo today has to discover the workflow by reading five different files in the
right order.

There is also no front door for the test suite itself. `tests/` has thirteen
test files and a non-trivial `conftest.py` with three autouse patches, several
singleton-reset gotchas, and a per-module coverage policy. New contributors
need a `tests/TEST_README.md` that surfaces the gotchas and points at
`docs/guides/testing.md` for the wider context.

## What Changes

- **`CONTRIBUTING.md`** at the repo root. Front-door document covering the
  contribution loop end-to-end: branch → OpenSpec proposal → implementation →
  tests → optional experiment → ADR (when architectural) → conventional commit
  → PR. Includes a Mermaid flow diagram, links to the existing deeper docs,
  and a "where to find things" reference table. Trivial fixes (typos,
  one-line bug fixes) get a documented shortcut that bypasses OpenSpec.
- **`tests/TEST_README.md`**. Test-suite front door covering quick-start
  commands, the per-file inventory, the conftest autouse patches, the
  reranker singleton reset, the EphemeralClient leak warning, the
  `METADATA_EXTRACTION_MODE` module-level patching note, and guidance for
  adding new tests. Cross-links to `docs/guides/testing.md` for the wider
  view and to `AGENTS.md` for the hard rules.
- **`README.md`**. Add a "Contributing" line under the documentation table
  pointing at `CONTRIBUTING.md` so the front door is discoverable from the
  landing page.
- No code changes. No test changes. No new dependencies.

## Capabilities

### New Capabilities

- `contributor-onboarding`: Single-page entry point that maps the
  contribution workflow (branch → propose → implement → test → ADR → PR)
  to the existing scaffolding (OpenSpec changes, ADRs, experiments,
  test gotchas) so a new contributor can find the right doc at each step
  without prior knowledge of the repo's conventions.

### Modified Capabilities

*(none — this change does not alter any spec-level system behaviour)*

## Impact

- New file: `CONTRIBUTING.md` (repo root)
- New file: `tests/TEST_README.md`
- Modified file: `README.md` (one-line addition to the docs table)
- No source code, tests, configuration, or CI files are affected.
- No new ADR is filed. ADRs in this repo record architectural tradeoffs
  (uv vs poetry, ChromaDB vs alternatives, async vs sync ingest);
  adding process documentation is housekeeping, not architecture.
  This decision is recorded explicitly here per the "no surprise" principle.
