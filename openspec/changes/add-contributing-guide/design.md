## Context

Process knowledge in this repo is well-documented but scattered. A new
contributor needs to read `AGENTS.md` (conventions, MCP rules, hard
boundaries), `docs/adr/ADR_README.md` (when and how to file ADRs),
`experiments/EXP_README.md` (when and how to add experiments),
`docs/guides/getting-started.md` (setup), and `docs/guides/testing.md`
(test suite) before they can confidently open a PR. There is no single
file that says "start here, then go there."

`CONTRIBUTING.md` is the conventional front door for this on GitHub —
the platform automatically links it from the PR creation flow and the
"Contribute" sidebar on the repo landing page. Adding it costs nothing
and removes a real friction point.

## Goals / Non-Goals

**Goals:**

- A new contributor can read `CONTRIBUTING.md` once and know the path
  from "I have an idea" to "my PR is open."
- Every step in the workflow links to the existing deeper doc — no
  duplication of conventions, install commands, or coverage thresholds.
- The test suite has its own front door (`tests/TEST_README.md`) with
  the gotchas surfaced where contributors will see them: in the test
  directory itself, not buried in `docs/guides/testing.md`.
- Trivial fixes have a documented shortcut so contributors do not file
  three-file OpenSpec proposals for typo fixes.

**Non-Goals:**

- Replacing `AGENTS.md`. AGENTS.md is the source of truth for AI agents
  and human contributors alike on conventions, MCPs, and hard rules.
  CONTRIBUTING.md links to it; it does not duplicate it.
- Replacing `docs/guides/testing.md`. That document covers the wider
  testing philosophy and per-module coverage policy. `tests/TEST_README.md`
  is a quick-reference and gotchas list that points at it.
- Adding a new ADR. ADRs in this repo record architectural decisions
  with alternatives and consequences; "we added a contributing guide"
  is housekeeping. The justification for the no-ADR call is recorded
  inline in `proposal.md` so future readers see the reasoning.
- Touching `getting-started.md` or duplicating its install commands in
  CONTRIBUTING.md. CONTRIBUTING links there for setup.

## Decisions

### Decision 1: One-page CONTRIBUTING.md with a Mermaid flow diagram

**Choice**: Single file, single diagram, prose around it that expands
each node with a one-or-two-sentence summary plus a link to the deeper
doc. Sections in this order: Welcome → Setup (link only) → The
Contribution Loop (diagram) → Workflow steps explained → Coding
conventions (link to AGENTS.md) → Commit and PR conventions →
PR checklist → Where to find things.

**Rationale**: The diagram does the structural work — anyone scanning
can see the whole flow in five seconds. The prose handles nuance
(when to skip OpenSpec, when an experiment is needed, when an ADR is
warranted). Multi-file contributing guides are a known anti-pattern;
they fragment the very thing they are trying to make discoverable.

**Alternative considered**: Split into `CONTRIBUTING.md` (overview) and
`docs/guides/contributing.md` (detail). Rejected — GitHub's `Contribute`
sidebar links to the root file, so the root file needs to be
self-contained for that surface to work.

### Decision 2: Trivial-fix shortcut explicit in the diagram

**Choice**: The flow diagram has a `Trivial fix?` decision node that
routes typos and one-line bug fixes straight to implementation,
bypassing OpenSpec.

**Rationale**: `AGENTS.md` already says OpenSpec is for "non-trivial"
changes. Without an explicit shortcut in CONTRIBUTING.md, contributors
either over-process trivial fixes (three-file proposal for a typo) or
skip OpenSpec for everything. The shortcut codifies what the existing
docs already imply.

**Alternative considered**: Require OpenSpec for all changes. Rejected
— would create friction disproportionate to the value of capturing
typo-fix history in a proposal.

### Decision 3: `tests/TEST_README.md` lives in `tests/`, not `docs/`

**Choice**: Put the test-suite front door inside the test directory
where contributors will land when they open the folder, not in
`docs/guides/`.

**Rationale**: Discovery. A contributor opening `tests/` to add a new
test sees `TEST_README.md` immediately. A `docs/guides/testing.md`
reader does not necessarily know the test directory layout. The two
docs serve different audiences: `tests/TEST_README.md` is for the
person about to write a test, `docs/guides/testing.md` is for the
person evaluating the testing strategy.

**Alternative considered**: Single source under `docs/guides/`.
Rejected — see above; co-location with the code reduces friction
when adding new tests.

### Decision 4: No ADR for this change

**Choice**: Document the no-ADR decision in `proposal.md`. Do not
create `docs/adr/015-contributing-guide.md`.

**Rationale**: ADRs in this repo record architectural decisions —
package manager choice, vector store choice, async vs sync ingest,
cross-encoder reranker. Each captures a tradeoff with rejected
alternatives and consequences. "Add a contributing guide" has no
architectural tradeoff to record; the alternatives (no guide, scattered
guide, multi-page guide) are documented here in design.md, which is
the right level of formality for a documentation decision.

**Alternative considered**: File ADR-015. Rejected — would dilute the
ADR signal-to-noise ratio. The ADR_README convention says "significant
architectural decisions"; this is not one.

### Decision 5: Mermaid for the diagram, not ASCII

**Choice**: Use a Mermaid `flowchart TD` block. GitHub renders it
natively.

**Rationale**: Renders inline on GitHub and most Markdown previewers
without external tooling. ASCII art does not scale past three or four
nodes. The diagram is the centrepiece of CONTRIBUTING.md; it deserves
to render properly.

**Alternative considered**: SVG export checked into `docs/`. Rejected
— turns a one-line diff into a binary asset and breaks `git diff`
when the flow changes. Mermaid is the right primitive here.

### Decision 6: `docs:` commit prefix

**Choice**: Single commit, message prefixed `docs:`.

**Rationale**: Per `AGENTS.md` release automation table, `docs:` does
not trigger a `python-semantic-release` version bump. This is correct
behaviour — adding a contributing guide should not cut a 0.x.y release.

## Risks / Trade-offs

- **Drift between CONTRIBUTING.md and the docs it links to**: If
  `AGENTS.md` or the workflow changes, CONTRIBUTING.md may go stale.
  → Mitigation: CONTRIBUTING.md links to deeper docs rather than
  duplicating their content. The diagram lives in one place. Drift
  surface is small.
- **Mermaid rendering on third-party tools**: GitHub renders Mermaid
  natively, but some IDE Markdown previewers do not. → Mitigation:
  acceptable. The primary surface is GitHub. Contributors not using
  GitHub's renderer will see the raw Mermaid source, which is still
  legible as a description of the flow.
- **Test discovery cost during pytest run**: Adding `tests/TEST_README.md`
  could in theory be picked up by pytest as a test target. → Mitigation:
  pytest's default `python_files = test_*.py` collection rule excludes
  `.md` files. Verified by inspection — no risk.
