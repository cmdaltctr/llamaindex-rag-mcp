## 1. Test-first configuration contract

- [x] 1.1 Add failing tests for the packaged pdf-inspector default and explicit reader resolution.
- [x] 1.2 Add coverage that confirms `auto` retains its existing fallback policy.

## 2. Configuration and dependency implementation

- [x] 2.1 Set the packaged PDF reader default in `config/` without changing environment override precedence.
- [x] 2.2 Promote pdf-inspector to the base dependency set while retaining the compatibility extra.
- [x] 2.3 Validate configured concrete readers through registry membership without reader-specific composition-root branches.

## 3. Contracts and documentation

- [x] 3.1 Update the baseline pdf-reader specification and its change delta.
- [x] 3.2 Create ADR-050 with Experiment 14 evidence and amend ADR-020.
- [x] 3.3 Update configuration, ingestion, architecture, and environment documentation.

## 4. Verification

- [x] 4.1 Run targeted tests and prove each new test fails before implementation.
- [x] 4.2 Run formatting, dependency-floor, strict OpenSpec, and focused security checks.
- [x] 4.3 Review the change for registry, configuration, and documentation drift.
