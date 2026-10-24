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

- [x] 3.1 Add the check step and the caution to ADR-094; note the reserved ADR-090 and ADR-091 in `ADR_README.md`; update `docs/guides/web-workspace.md`. Verify: docs tests pass.
- [x] 3.2 Re-pin the clean-base tripwire if the counts move. Run `./scripts/local_ci.sh` and `openspec validate harden-integration-installs --strict`. Verify: both pass.
  - Result (2026-10-24): fast suite 7,806 passed, 152 skipped; tripwire 5 passed (pin 7,813 = measured 7,806 + 7; `_WEB_EXTRA_CASES` 1,360); web 152 files, 1,858 tests; OpenSpec 86 passed; local CI passed.
- [x] 3.3 Browser check at 1280 px and 390 px on a scratch server: the Anthropic callout shows and fits. Verify: no sideways scroll.
  - Result (2026-10-24): scratch checkout server on port 8793. At 1280 px the red "Before you install" callout shows on the Anthropic card only (1 of 12 cards), above the copy command, border `rgb(218, 91, 74)`. At 390 px it stays inside the card (324 px wide) and the page has no sideways scroll.
