# TDR-007: CI quality toolchain consolidation — Ruff, CodeRabbit, and Codecov replace SonarCloud

**Date:** 2026-08-10
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Supersedes:** TDR-002
**Tags:** ci | lint | security | coverage | ruff | coderabbit | codecov | sonarcloud

## Context

TDR-002 established SonarCloud as the single analysis backend covering
security, code quality, and coverage. It ran via a `sonarcloud` job in
`ci.yml` using `SonarSource/sonarqube-scan-action`, configured by
`sonar-project.properties`. Before 2026-08-10 the CI pipeline had no
dedicated lint gate: quality enforcement was delegated entirely to
SonarCloud, which also received the only coverage report.

Three changes landed the same day that made SonarCloud redundant:

1. **PR #28** (`ci/add-ruff-lint-gate`) added a Ruff lint/format gate, a
   `lint` job in `ci.yml`, pre-commit hooks, and committed a
   `.coderabbit.yaml` configuring CodeRabbit with BetterLeaks (secrets)
   and OpenGrep (static analysis) enabled and Semgrep disabled.
2. **PR #29** (`ci/replace-sonarcloud-with-codecov`) replaced the
   `sonarcloud` job with a `codecov` job and added `codecov.yml`.
3. Review of SonarCloud's own findings showed they were stale: all 60
   unresolved issues pointed at v1 files deleted in the v2.0.0 refactor
   (`code_graph.py`, `codebase_map.py`, `doc_graph.py`, `ingestion.py`,
   `cli.py`, etc.). Zero security vulnerabilities and zero hotspots
   across the whole project history. 55 of the 60 code smells mapped
   directly to Ruff rules (`C901`, `UP031`, `ARG`, `B904`, `F401`,
   `F841`).

The only non-redundant function SonarCloud performed was coverage gating
on new code (pytest has no `fail_under` in CI). Codecov is purpose-built
for that job.

## Decision

Replace the single SonarCloud gate with three specialised tools, each
focused on one concern:

| Concern | Tool | Where it runs |
| ------- | ---- | ------------- |
| Lint + format | Ruff | `lint` CI job + pre-commit hooks |
| AI review + secrets + static analysis | CodeRabbit (BetterLeaks, OpenGrep) | PR reviews via `.coderabbit.yaml` |
| Coverage gating | Codecov | `codecov` CI job + `codecov.yml` |

### Ruff (PR #28)

`[tool.ruff]` in `pyproject.toml`: line length 100, target py311,
`E F I UP B S` rule set, `tests/*` per-file ignores for `S101`/`S108`/
`B017`/`S603`/`S607`. The `lint` CI job runs `ruff check .` and
`ruff format --check .`. `.pre-commit-config.yaml` runs Ruff locally.

### CodeRabbit (PR #28)

`.coderabbit.yaml` is committed to version control for PR-time
transparency. Security-relevant tools: `gitleaks` (BetterLeaks secrets
scanning) enabled, `opengrep` enabled, `semgrep` disabled. Path-scoped
instructions encode the repo's architecture invariants (config leaf
rule, ingestion/retrieval no-cross-import, thin transports, MCP
handlers never raise) so the reviewer enforces them like a human who
knows the codebase. Reviews run on `main` and `v3`.

### Codecov (PR #29)

The `sonarcloud` job is replaced by a `codecov` job that generates
branch coverage and uploads it:

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

`codecov.yml` mirrors the AGENTS.md coverage tiers as hard minimums (no
threshold softening):

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

- Each tool is best-in-class for its single concern instead of one tool
  doing all three poorly
- Coverage gating is done by a tool whose core product it is, with
  diff-aware PR comments and a dashboard
- Branch coverage (`--cov-branch`) is now measured — more accurate than
  the line-only coverage SonarCloud received
- CodeRabbit's committed config enforces architecture invariants on
  every PR, catching cross-import and handler-raises violations at
  review time
- Ruff catches issues locally via pre-commit, before CI cost
- Removes a stale analysis that reported on deleted files

### Negative

- Three tools instead of one — more configuration surface to maintain
- SonarCloud's cognitive-complexity metric (S3776) is no longer tracked;
  Ruff `C901` covers cyclomatic complexity only
- SonarCloud duplicated-literal (S1192) and always-returns-same-value
  (S3516) rules have no Ruff equivalent — accepted, both were on deleted
  v1 code
- Secrets and static-analysis scanning now happen at PR-review time via
  CodeRabbit rather than as a dedicated CI job — a review miss is not
  caught by an independent scan
- `SONAR_TOKEN` remains as a dormant secret until manually removed

### Neutral

- Local `sonar` CLI stays installed for ad hoc secrets scanning
- `sonar-project.properties` exclusions (`experiments/**`,
  `chroma_db/**`) are mirrored by the `ignore:` block in `codecov.yml`

## Alternatives Considered

| Option | Rejected Because |
| ------ | ---------------- |
| Keep SonarCloud, re-run analysis | Analysis was stale on deleted files; zero security findings; 55/60 smells already covered by Ruff — no unique value left beyond coverage |
| Semgrep as a dedicated CI SAST job | OpenGrep (Semgrep's open-source fork) inside CodeRabbit covers the static-analysis need at review time without another CI service |
| Codecov CLI instead of the Action | The v5+ Action wraps the CLI internally; the CLI adds boilerplate only useful outside GitHub Actions |
| pytest-cov `fail_under` in CI | Duplicates what Codecov's project status checks already enforce, without the PR comment and dashboard |

## How to Recognise / Handle This Again

1. **Coverage check not appearing on a PR**: Verify the Codecov job ran
   and the repo is activated at `https://app.codecov.io/gh/cmdaltctr`.
   Check `CODECOV_TOKEN` is set:
   `gh secret list --repo cmdaltctr/llamaindex-rag-mcp`.
2. **Ruff gate failing**: Run `uv run ruff check .` and
   `uv run ruff format --check .` locally. Fix, or add a per-file ignore
   to `pyproject.toml` if the rule is a deliberate exception.
3. **CodeRabbit not reviewing a PR**: Check the PR targets `main` or
   `v3` (see `base_branches` in `.coderabbit.yaml`) and that the branch
   is not a draft. Verify the app is installed on the repo.
4. **Coverage gate too strict / too loose**: Edit targets in
   `codecov.yml` under `coverage.status.project`. Keep them aligned with
   the AGENTS.md coverage table — they are hard minimums by design.
5. **Coverage report missing lines or files**: Check the `ignore:` block
   in `codecov.yml` and that `--cov=rag_mcp --cov-branch
   --cov-report=xml` is present in the `codecov` job.

## Revisit Triggers

- **Ruff adds cognitive-complexity support**: Reconsider whether the lost
  S3776 metric needs a replacement.
- **Security posture moves beyond PR-time review**: If the project needs
  independent SAST in CI (not review-gated), evaluate a dedicated
  Semgrep/OpenGrep CI job.
- **Codecov price or rate limits change**: Reevaluate against pytest-cov
  `fail_under` plus a simpler upload.
- **Coverage targets drift from reality**: If the project check blocks
  legitimate PRs repeatedly, re-baseline the targets in `codecov.yml`
  rather than adding a `threshold` back.

## References

- PR #28: `https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/28`
- PR #29: `https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/29`
- TDR-002: `docs/tdr/002-sonarcloud-security-gate-via-github-actions.md`
- `.coderabbit.yaml` — CodeRabbit config (BetterLeaks, OpenGrep)
- `.pre-commit-config.yaml` — local hooks
- `pyproject.toml` — `[tool.ruff]` config
- `.github/workflows/ci.yml` — `lint` and `codecov` jobs
- `codecov.yml` — coverage gates
- AGENTS.md — Coverage Thresholds table (95%/85%/90%)
- Codecov quick start: `https://docs.codecov.com/docs/quick-start`
