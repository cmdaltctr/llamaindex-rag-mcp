---
description: Create a systematic conventional commit with staged analysis, type selection, scoping, and quality checks. Usage: /commit [description]
---

You are creating a Conventional Commit following the specification.

## User Input

```text
$ARGUMENTS
```

## Workflow Steps

### 1. Analyse changes

Run `git status` and `git diff --staged` to understand what has changed. If nothing is staged, check unstaged changes with `git diff`.

### 2. Categorise changes

Group changes by:
- **Type of change** (see table below)
- **Scope** (which part of the codebase)
- **Related changes** (can be committed together)

### 3. Determine commit type

| Type | Description | Usage |
|------|-------------|-------|
| **feat** | A new feature for the user | New functionality |
| **fix** | A bug fix for the user | Bug fixes |
| **chore** | Maintenance (deps, configs) | Tooling, dependencies |
| **docs** | Documentation only | README, comments |
| **refactor** | Code change, not bug or feature | Restructuring |
| **perf** | Performance improvement | Optimisation |
| **test** | Adding or correcting tests | Test files |
| **style** | Formatting only | Code style |
| **ci** | CI configuration | Pipelines |
| **build** | Build system or deps | Build tools |

### 4. Write commit message

Format: `type(scope): description`

Rules:
- Use imperative mood ("add" not "added")
- Be concise but descriptive
- Start lowercase (after colon)
- No period at end
- Add body for complex changes (explain WHY)
- Add footer for breaking changes (`BREAKING CHANGE:`) or issues (`Closes #123`)

### 5. Stage and commit

Stage files systematically — one logical group per commit. Never mix features with fixes.

### Quality checks before committing
- [ ] No `console.log` statements
- [ ] No hardcoded secrets or API keys
- [ ] No `any` types in TypeScript
- [ ] All tests pass

### Output
```
✓ Committed: type(scope): description
  SHA: {hash} | Files: {n} changed
```
