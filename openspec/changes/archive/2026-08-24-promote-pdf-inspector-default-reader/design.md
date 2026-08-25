## Context

`PDF_READER` is a cross-cutting setting owned by `config/`. Its packaged value
is currently `auto`, which selects LiteParse where available. The existing PDF
registry already contains a lazy `pdf_inspector` adapter. Experiment 14
supports selecting it as the packaged default.

## Goals / Non-Goals

**Goals:**
- Make `pdf_inspector` the shipped default through configuration.
- Keep each reader selectable through `PDF_READER`.
- Preserve the existing `auto` capability fallback and explicit overrides.
- Resolve configured concrete readers without reader-specific branches.

**Non-Goals:**
- Change the `auto` fallback preference policy.
- Change PDF chunking, OCR routing, or reader output shapes.
- Remove LiteParse, pypdfium2, or pypdf support.

## Decisions

### Keep selection in configuration

Set the packaged `PDF_READER` value to `pdf_inspector`. Environment and
constructor settings continue to override it. This makes a reader change a
configuration edit rather than a code-path edit.

### Retain the registry as dispatch authority

The composition root will validate configured concrete readers through
registry membership before probing their packages. It will not add a
`pdf_inspector` name check. `auto` retains its current fallback policy because
it is an explicit capability policy, separate from the packaged default.

### Make the packaged default available in the base install

Move the existing `pdf-inspector` dependency to `[project.dependencies]`.
Retain its optional-extra name as a compatibility alias for existing install
commands. This follows ADR-020's promotion model for LiteParse.

### Preserve safe fallback

If a configured concrete reader cannot be imported, resolution logs an error
and returns pypdf. Operators can roll back without code changes by setting
`PDF_READER=liteparse`, `pypdfium2`, `pypdf`, or `auto`.

## Risks / Trade-offs

- Native wheel availability → retain pypdf fallback and test missing-reader resolution.
- One source document per PDF → retain Experiment 14 evidence; do not alter chunking here.
- Base dependency size increases → the wheel is small and replaces an already-supported optional installation.

## Migration Plan

1. Add failing tests for configured pdf-inspector resolution and defaults.
2. Promote the existing dependency and update configuration defaults.
3. Use registry metadata for configured reader resolution.
4. Update user documentation and ADR-020 with ADR-050.
5. Validate targeted tests, strict OpenSpec, and dependency-floor checks.

Rollback: set `PDF_READER=liteparse` or `PDF_READER=pypdf` in the operator environment.
