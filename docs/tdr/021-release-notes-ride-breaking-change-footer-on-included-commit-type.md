# TDR-021: Release notes must ride a `BREAKING CHANGE` footer on an included commit type

**Date:** 2026-09-01
**Status:** Accepted
**Deciders:** Aizat
**Tags:** release | changelog | semantic-release | ci

## Context

Releases are cut by `python-semantic-release` on every push to `main`
(`AGENTS.md`, "Release Automation"). The configuration in `pyproject.toml`:

- parses Conventional Commits (`minor_tags = ["feat"]`,
  `patch_tags = ["fix", "perf"]`; `feat!:` or a `BREAKING CHANGE:` footer
  forces a major),
- generates `CHANGELOG.md` from commits (the file carries the
  `<!-- version list -->` generator marker),
- **excludes** `chore:`, `ci:`, `refactor:`, `style:`, `test:`,
  `build:` (non-deps), and `docs:` commits from the changelog,
- parses squash commits, ignores merge commits.

Change `fix-embedding-and-structure-fidelity-1` needed a user-facing release
notice: the release invalidates every stored vector and forces a full
re-ingest. The obvious places for that notice do not work:

1. Editing `CHANGELOG.md` by hand — the generator owns the file; manual
   entries are lost on the next release.
2. A `docs:` commit mentioning the re-ingest — excluded from the changelog by
   configuration, so it never reaches a release note.
3. Relying on the PR body — not parsed by the release tooling at all.

### Root Cause Analysis

Not a bug: the toolchain is behaving as configured. The gap is that the
configuration makes commit **type** carry release semantics, while
human instinct is to put prose announcements in documentation commits. The
notice must travel on a commit type the parser includes.

## Decision

A release-facing notice is attached as a `BREAKING CHANGE:` footer on a commit
whose type the changelog includes (`feat`, `fix`, `perf`; `feat!:` when the
major bump is intended). For change 1, the notice rode the stage-E commit
`37d3029` (`feat!:`), which both surfaced the notice and forced the major.

Two operational rules follow:

1. **Merge method matters.** This repo merges PRs with merge commits
   (PRs #75, #76, #79), so the footer-bearing commits survive into the
   branch history that semantic-release later parses. A squash-merge of a
   footer-bearing PR must preserve the type, the `!`, and the footer in the
   squash message, or both the notice and the major bump are lost.
2. **Releases fire on `main` only.** PR #79 merged into `v3`; the bump and
   the changelog entry land later, when `v3` merges into `main`. The footer
   travels with the commits until then.

Example footer (as used on `37d3029`):

```
feat!: <subject>

<body>

BREAKING CHANGE: every previously ingested source re-processes on the next
corpus ingest. ...
```

## Consequences

### Positive

- The re-ingest requirement reaches the generated changelog with no manual
  file ownership.
- The major bump is derived, not hand-picked — version and notice cannot
  drift apart.

### Negative

- A `docs:`-only change that needs a release note must either ride along
  with a feature commit or deliberately use a `feat`/`fix` type for a
  release-note commit, which slightly abuses the type semantics.
- Squash-merge workflows need discipline (or a CI check) to preserve
  footers.

### Neutral

- `style:`, `test:`, and `docs:` commits remain invisible to the changelog,
  which is the desired quiet-by-default behaviour.

## How to Recognise / Handle This Again

1. **Symptom**: a user-facing migration step (re-ingest, env var rename,
   breaking API change) shipped without appearing in `CHANGELOG.md`.
2. **Diagnostic**: `git log --format="%s%n%b" <last_release>..HEAD` — check
   the notice exists as a `BREAKING CHANGE:` footer and that its commit type
   is not in `exclude_commit_patterns`.
3. **Recovery**: cherry-pick or revert-and-recommit the notice onto a
   `feat!:`/`fix:` commit before the next release runs.

## Revisit Triggers

- `exclude_commit_patterns` or the parser options in `pyproject.toml`
  change.
- The repo switches its default merge method to squash.
- `semantic-release` configuration gains an `env`/`mask` or
  release-notes-template mechanism that supersedes footer parsing.

## References

- Config: `pyproject.toml` sections `[tool.semantic_release*]`
- Notice in use: commit `37d3029`, PR #79 (merged `b498f60`)
- Upgrade documentation: `docs/guides/ingestion.md` → "Upgrading to this
  release"
- Related: ADR-055 (the contract the notice announces)
