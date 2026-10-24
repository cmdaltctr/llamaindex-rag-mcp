# Tasks

## 1. Server

- [x] 1.1 Run `uv pip check --python <own Python>` after a successful install; a conflict gives `failed` with `check-failed`. Verify: fake `uv` tests for a passing check, a failing check (no `restart_needed`, check lines kept) and no check after a failed install. Each fails before the code.
- [x] 1.2 Return `status-unknown` for an `unknown` entry, with a 409 line in `REASONS`. Verify: an environment test and a route test (409, no process). Both fail before the code.
- [x] 1.3 Add `install_caution` to the catalogue entry and set the Anthropic text. Verify: a catalogue test for Anthropic and for an entry without one.
- [x] 1.4 Add the metadata guard test. Verify: the guard fails on fabricated `or` and `omrs` lines and passes on the real metadata.
- [x] 1.5 Update `openapi.yaml` (`install_caution`, `status-unknown`, `check-failed`). Verify: the OpenAPI conformance tests pass.

## 2. Page

- [x] 2.1 Load the `omrs-design` skill. Show `install_caution` as a red callout on the card while the entry is `not-installed` or `unknown`. Verify: Vitest cases for shown and hidden, failing first.
- [x] 2.2 Add the `check-failed` failure line and the `status-unknown` refusal line. Verify: Vitest cases, failing first.

## 3. Records and checks

- [ ] 3.1 Add the check step and the caution to ADR-094; note the reserved ADR-090 and ADR-091 in `ADR_README.md`; update `docs/guides/web-workspace.md`. Verify: docs tests pass.
- [ ] 3.2 Re-pin the clean-base tripwire if the counts move. Run `./scripts/local_ci.sh` and `openspec validate harden-integration-installs --strict`. Verify: both pass.
- [ ] 3.3 Browser check at 1280 px and 390 px on a scratch server: the Anthropic callout shows and fits. Verify: no sideways scroll.
