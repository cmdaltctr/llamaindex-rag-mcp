# Tasks

Run every command from the worktree root. Check `git branch --show-current` first. Each task that adds a test follows this order: write the test, run it, confirm that it fails for the right reason, then implement.

## 1. Planning

- [x] 1.1 Write the proposal, design, spec deltas and tasks. Fix the baseline `web-login-item` scenario "Restart signs the browser out", which this change makes wrong. Verify: `openspec validate persistent-web-auth-token --strict` passes.
- [x] 1.2 Write ADR-088 and add it to the ADR index. Add an amendment note to ADR-085. Verify: the ADR index links resolve.

## 2. Server

- [x] 2.1 Test first: `tests/unit/test_web_page_secret.py` covers the secret file (0600, folder 0700, reuse, loose mode, broken file), the page rule (own origin, approved origin, foreign `Host`, foreign `Origin`, cross-site fetch), restart acceptance with a new app on the same workspace, the failure limit, the unused login-item link, and the secret in no log, body or terminal. Verify: the module fails to import before `page_secret.py` exists.
- [x] 2.2 Move `validate_bind_host` to `transports/api/bind_address.py`. Update the imports in `app.py`, `cli/web.py` and `tests/unit/test_web_security.py`. Verify: `tests/unit/test_web_security.py` passes.
- [x] 2.3 Add `AccessPolicy.open_session()` and use it in `exchange_bootstrap`. Verify: `security.py` stays under 500 lines and the security and launch-link tests pass.
- [x] 2.4 Add `transports/api/page_secret.py` with `PageSecret`, `page_may_carry_secret` and `inject_page_secret`. Wire it into `FrontendFallback`, `create_app` (`page_secret=`), `POST /v1/session` and `omrg web`. Verify: task 2.1 passes.
- [x] 2.5 Check that each new test fails when the code it covers is broken: drop the `Host` and `Origin` rule, drop the 401 retry, route the page secret through `exchange_bootstrap`. Verify: the matching tests fail, then pass again after the revert.
- [x] 2.6 Change the `omrg web restart` message and docstring. Update the `POST /v1/session` description in `openapi.yaml`. Verify: the OpenAPI conformance tests pass.
- [x] 2.7 Add the new fast cases to `_BASE_EXECUTED` and `_WEB_EXTRA_CASES` in `tests/test_clean_base_tripwire.py`, with a dated comment.

## 3. Front end

- [x] 3.1 Test first: `web/src/api/session.test.ts` covers `takePageSecret`, `createSessionRenewer` (one shared request), `startSession` (link first, then the page secret) and the client retry (one sign-in, one retry, no retry on 403, no change without a renewer). Verify: the new cases fail before the code exists.
- [x] 3.2 Add the page-secret functions to `api/bootstrap.ts`, the renewer argument to `createApiClient`, the `renewSession` prop to `ApiProvider`, and wire `main.tsx`. Verify: task 3.1 passes.
- [x] 3.3 Change the copy that said the browser is signed out: `PowerMenu.tsx`, `RestartDialog.tsx`, and the 401 message in `lib/errors.ts`. Update their tests. Verify: `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.

## 4. Docs

- [x] 4.1 Update `docs/guides/web-workspace.md` (sign-in, login item, power menu), `docs/guides/cli-reference.md` (restart) and the module table in `src/omrg/transports/api/README.md`. Verify: `tests/unit/test_web_workspace_guide.py` passes.

## 5. Checks

- [x] 5.1 Start `omrg web` from the worktree on a free port with a throwaway workspace. Sign in once, restart the server, and confirm that the open tab keeps working with no sign-in step. Stop the server.
- [x] 5.2 Run `env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY ./scripts/local_ci.sh`. Verify: it ends with `== local CI passed ==`.
- [x] 5.3 Archive the change and sync the specs. Verify: `openspec validate --all --strict` passes.
