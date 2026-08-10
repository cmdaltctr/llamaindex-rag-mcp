# TDR-007: Codecov replaces SonarCloud for coverage gating

**Date:** 2026-08-10
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Supersedes:** TDR-002
**Tags:** ci | coverage | codecov | sonarcloud

## Context

TDR-002 established SonarCloud as the analysis backend for security, code
quality, and coverage reporting. It runs via a `sonarcloud` job in
`ci.yml` using `SonarSource/sonarqube-scan-action`, configured by
`sonar-project.properties`.

During a review of SonarCloud's value against Ruff and CodeRabbit, the
following evidence emerged:

1. All 60 unresolved SonarCloud issues pointed at v1 files deleted in the
   v2.0.0 refactor (`code_graph.py`, `codebase_map.py`, `doc_graph.py`,
   `ingestion.py`, `cli.py`, etc.). The analysis had not been re-run since
   the refactor and was entirely stale.
2. Zero security vulnerabilities and zero security hotspots across the
   whole project history — the one capability neither Ruff nor CodeRabbit
   provides produced nothing.
3. 55 of 60 code smells map directly to Ruff rules (`C901`, `UP031`,
   `ARG`, `B904`, `F401`, `F841`).

The only non-redundant function SonarCloud performed was coverage gating
on new code, because pytest has no `fail_under` in CI. Codecov is
purpose-built for that job.

## Decision

Replace SonarCloud with Codecov for coverage gating. Keep Ruff (lint) and
CodeRabbit (review) for code quality. Implemented in PR #29
(`ci/replace-sonarcloud-with-codecov`, merged 2026-08-10, commit `14acd22`).

### CI: Codecov job

The `sonarcloud` job in `.github/workflows/ci.yml` is replaced by a
`codecov` job that generates branch coverage and uploads it:

```yaml
- name: Run tests with coverage
  run: uv run --no-sync pytest -m "not slow" --cov=rag_mcp --cov-branch --cov-report=xml

- name: Upload coverage to Codecov
  uses: codecov/codecov-action@e53489f4d376d79066609109e7a95a29eb3740b1
  with:
    files: ./coverage.xml
    token: ${{ secrets.CODECOV_TOKEN }}
    fail_ci_if_error: true
```

The action is pinned to the v7.0.0 SHA, matching the repo's SHA-pinning
pattern. The job sets `permissions: contents: read` (least privilege).

### Coverage gates: `codecov.yml`

New `codecov.yml` mirrors the AGENTS.md coverage tiers as hard minimums
(no threshold softening):

| Check | Target |
| ----- | ------ |
| Project — core + MCP paths | 95% |
| Project — orchestration paths (daemon, CLI) | 85% |
| Project — default (overall) | 90% |
| Patch (new code) | 90% |

`sonar-project.properties` is deleted. `CODECOV_TOKEN` is stored as a
GitHub Actions secret. The `SONAR_TOKEN` secret is retained but unused.

## Consequences

### Positive

- Coverage gating is now done by a tool whose core product it is
- Diff-aware PR coverage comments from Codecov
- Branch coverage (`--cov-branch`) is now measured — more accurate than
  the line-only coverage SonarCloud received
- Removes a stale analysis that reported on deleted files
- One fewer CI service and one fewer secret in use

### Negative

- SonarCloud's cognitive-complexity metric (S3776) is no longer tracked;
  Ruff `C901` covers cyclomatic complexity only
- SonarCloud duplicated-literal (S1192) and always-returns-same-value
  (S3516) rules have no Ruff equivalent — accepted, both were on deleted
  v1 code
- `SONAR_TOKEN` remains as a dormant secret until manually removed

### Neutral

- Local `sonar` CLI stays installed for ad hoc secrets scanning
- `sonar-project.properties` exclusions (`experiments/**`, `chroma_db/**`)
  are mirrored by the `ignore:` block in `codecov.yml`

## Alternatives Considered

| Option | Rejected Because |
| ------ | ---------------- |
| Keep SonarCloud, re-run analysis | Analysis was stale on deleted files; zero security findings; 55/60 smells already covered by Ruff — no unique value left beyond coverage |
| Codecov CLI instead of the Action | The v5+ Action wraps the CLI internally; the CLI adds boilerplate only useful outside GitHub Actions |
| pytest-cov `fail_under` in CI | Duplicates what Codecov's project status checks already enforce, without the PR comment and dashboard |

## How to Recognise / Handle This Again

1. **Coverage check not appearing on a PR**: Verify the Codecov job ran
   and the repo is activated at `https://app.codecov.io/gh/cmdaltctr`.
   Check `CODECOV_TOKEN` is set: `gh secret list --repo cmdaltctr/llamaindex-rag-mcp`.
2. **Coverage gate too strict / too loose**: Edit targets in `codecov.yml`
   under `coverage.status.project`. Keep them aligned with the AGENTS.md
   coverage table — they are hard minimums by design.
3. **Coverage report missing lines or files**: Check the `ignore:` block
   in `codecov.yml` and that `--cov=rag_mcp --cov-branch --cov-report=xml`
   is present in the `codecov` job.
4. **New project needs coverage**: Copy the `codecov` job from `ci.yml`,
   add `codecov.yml`, set a `CODECOV_TOKEN` secret, activate the repo on
   Codecov.

## Revisit Triggers

- **Ruff adds cognitive-complexity support**: Reconsider whether the lost
  S3776 metric needs a replacement.
- **Codecov price or rate limits change**: Reevaluate against pytest-cov
  `fail_under` plus a simpler upload.
- **Coverage targets drift from reality**: If the project check blocks
  legitimate PRs repeatedly, re-baseline the targets in `codecov.yml`
  rather than adding a `threshold` back.

## References

- PR #29: `https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/29`
- TDR-002: `docs/tdr/002-sonarcloud-security-gate-via-github-actions.md`
- `.github/workflows/ci.yml` — `codecov` job
- `codecov.yml` — coverage gates
- AGENTS.md — Coverage Thresholds table (95%/85%/90%)
- Codecov quick start: `https://docs.codecov.com/docs/quick-start`
