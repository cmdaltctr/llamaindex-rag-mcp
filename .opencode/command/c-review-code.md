---
description: Full code quality review with security audit, test coverage check, and spec compliance. Usage: /review-code <change-id> [--deep]
agent: a-review
subtask: true
---

You are running a comprehensive code review.

## Pre-flight

1. **Load the review orchestrator prompt** — internalise delegation rules:
   Read `~/.config/opencode/prompts/a-review-orchestrator.txt`

2. **Load relevant skills** for the tech stack:
   ```
   skill({ name: "typescript" })
   skill({ name: "cloudflare" })
   ```

## Parse Input

- Change ID: $1 (kebab-case, e.g. "add-oauth")
- Flag `--deep` → also run @a-deep-search for thorough codebase tracing

## Load Context

Read ALL available:

- `openspec/changes/$1/proposal.md` — What was supposed to be built
- `openspec/changes/$1/specs/*/spec.md` — SHALL/MUST requirements
- `openspec/changes/$1/evaluation.md` — Acceptance criteria
- `openspec/changes/$1/risks.md` — Prior security findings (if exists)

## Execute Review Workflow

For the change type:

- **Auth / Payments / Security-sensitive** → @a-security audit (MUST)
- **New dependencies introduced** → @a-tech-researcher CVE check (MUST)
- **Large codebase change** → @a-explore or @a-deep-search
- **Test coverage concerns** → @a-test (if coverage < 80%)

Spawn parallel where independent.

## Output Format

```markdown
## Review Summary: $1
### Verdict: APPROVED / NEEDS CHANGES / BLOCKED
### Findings
[CRITICAL/HIGH/MEDIUM/LOW severity issues with file locations]
### Required Before Merge
- [ ] Item 1
### Optional Improvements
- [ ] Item 2
```
