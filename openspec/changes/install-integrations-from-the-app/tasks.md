# Tasks

Implement after `add-chat-reasoning-and-usage`, in the same worktree.

## 1. Install type and copy commands

- [x] 1.1 Add install type detection (`uv-tool`, `checkout`, `other`), receipt parsing and `uv` lookup. Verify: unit tests with a fake receipt in a tmp folder, a fake checkout and neither. Each fails before the code.
- [x] 1.2 Return the correct copy command for each install type, with `~` for the home folder. Verify: tests for the three command forms, including the receipt extras plus the new extra.
- [x] 1.3 Report `installable` and its reason on each catalogue entry; exclude `web` and `torch`. Verify: tests for an allowed extra, an excluded extra, and `uv` not found.

## 2. Install job

- [x] 2.1 Read the extra's requirements from the installed package metadata. Verify: a test that `anthropic` gives `llama-index-llms-anthropic>=0.11.0` with no marker, and an unknown extra gives nothing.
- [x] 2.2 Add `InstallJob` on `WebRuntime`: one job at a time, argument list with no shell, environment without `*_API_KEY`, 40-line redacted output, 600 s timeout, `restart_needed` set. Verify: tests with a fake `uv` script for success, failure, timeout and a second start while running; a test that a key value in the output is redacted.
- [ ] 2.3 Live check on a scratch `uv tool` environment, never the live login item: install `anthropic`, restart, and confirm the provider reports installed. Record the time taken.

## 3. Routes

- [x] 3.1 Add `POST /v1/integrations/{extra}/install` (`manage` session only) and `GET /v1/integrations/install`. Verify: route tests for 202, 404 unknown, 409 excluded, 409 running, 409 not `uv-tool`, and 403 for a bearer token.
- [x] 3.2 Update the OpenAPI 3.1 contract and its contract test.

## 4. Integrations page

- [x] 4.1 Load the `omms-design` skill. Add the Install button, confirm dialog, progress line, output block and Restart action to `IntegrationCard`. Verify: Vitest cases from the spec scenarios fail first, then pass.
- [x] 4.2 Poll the install status only while `running`. Verify: a Vitest case that no request is sent while idle.
- [x] 4.3 Update the page text about installing and restarting, and `docs/guides/web-workspace.md`. Verify: lint and typecheck pass.

## 5. Provider cards

- [x] 5.1 Replace the printed command on a not-installed provider card with a link to its Integrations entry; use the same link in the Chat and judge fix line. Verify: Vitest cases for installed and not installed.
- [x] 5.2 Update `docs/guides/cli-reference.md` with the lasting `uv tool install --reinstall` command. Verify: the docs drift check passes.

## 6. Records and checks

- [x] 6.1 Write the ADR for app-driven installs of allowed extras (load `s-adr`), with the next free number, and add it to the index.
- [ ] 6.2 Run `./scripts/local_ci.sh`, `npm run lint`, `npm run typecheck`, `npm test` in `web/`, and `openspec validate install-integrations-from-the-app --strict`. Verify: all pass.
- [ ] 6.3 Browser check on the scratch server at 1280 px and 390 px: install one extra, restart, and see it reported available.
