# Tasks

Builds on the uncommitted `redesign-web-workspace` code in the same worktree. Work in the `feat/redesign-web-workspace` worktree (`llamaindex-rag-mcp-feat-redesign-web-workspace`).

## 1. Run artefact route

- [x] 1.1 Write failing tests in `tests/unit/test_web_run_artefacts.py`: a cut node summary is returned in full; an unknown name gives 404 with a generic message; names with `/`, `\`, `..` or `.` give 400 and read no file; an unknown run gives 404; a bearer credential bound to one experiment cannot read an artefact of another experiment's run or of a live run; the response holds no credential value and no raw vector.
- [x] 1.2 Add `GET /v1/runs/{run_id}/artefacts/{name}` in `src/omrg/transports/api/routes_runs.py` per design D1, reusing `_graph_run` and `ArtefactStore.read_json`; make the tests pass and break-check the visibility and the name check.
- [x] 1.3 Add the operation and its response schema to `openapi.yaml`, add it to the OpenAPI conformance families, and document it in `docs/guides/web-workspace.md` and `src/omrg/transports/api/README.md`.
- [x] 1.4 Save a cut step summary in `finish()` (`src/omrg/core/workspace/outcomes.py`) through `ArtefactStore.safe_summary`, so it carries `truncated: true` and `artefact_ref`; test it in `tests/unit/test_workspace_service_outputs.py` and break-check it.

## 2. Open full output in the run detail

- [x] 2.1 Add `getRunArtefact(api, runId, name)` to `web/src/api/runs.ts` and `runArtefactQuery` to `web/src/api/queries.ts`, with tests for the path, the name check and the run-part match of an `artefact_ref`.
- [x] 2.2 Build `OutputViewer` per design D3 (Dialog primitive, plain-text JSON, client masking, 256 KiB display limit with a stated cut, Download with a revoked object URL, `ErrorNotice` with Retry); test the cut statement, the download content, markup shown as text, and a failed load.
- [x] 2.3 Offer "Open full output" on every cut preview in `web/src/experiments/runs/` (node and status summaries through the route; the stored result and evidence rows from memory, per design D2); a summary whose `artefact_ref` names another run shows as cut without the action. Test each kind against the run fixtures.
- [x] 2.4 Check the run detail with an opened viewer at 1280 px and 390 px in both themes, and store the 1280 px captures in the guide; confirm no horizontal page scroll and a visible focus ring on the action and the dialog controls.

## 3. Upload limit in Settings

- [x] 3.1 Write failing tests for `WorkspaceSettings`: `upload_limit_mib` round-trips; `None` clears it; 0, 2049 and non-numeric stored text read as unset; setting a value out of range raises `ValueError`. Add the key and the two methods per design D4.
- [x] 3.2 Write failing tests in `tests/unit/test_web_upload_limit.py`: `GET` returns the default 50 MiB with `saved_mib: null` and the range; `PUT` with 200 then lets a 120 MiB declared upload pass preflight without a restart; a new app on the same workspace starts with 200 MiB; `PUT null` returns to 50 MiB; 0, 4096, `1.5`, `"10"` and an extra field give 400 and change nothing; a bearer credential is refused; an upload started before a lowered limit finishes against its start limit. Implement the routes, the startup read in `lifespan.py` and the single-read limit in `UploadStore.receive`; break-check the session-only scope, the write-before-apply order and the in-flight rule.
- [x] 3.3 Write failing tests for the launch option: `--max-upload-mib 400` beats `WEB_MAX_UPLOAD_MIB=300`, which beats a saved 200; `0`, `5000` and `big` exit with code 2 before a port is bound and name the option and range; with a launch value `GET` reports `source: "launch"` and `PUT` answers 409 and changes nothing. Add the option, `WebConfig.launch_upload_limit_mib` and the source to the runtime; break-check the order and the 409.
- [x] 3.4 Add `WEB_MAX_UPLOAD_MIB` to `.env.example` in a new `omrg web` section; update the `omrg web` section of `docs/guides/cli-reference.md` (options list, order of the limit sources) and its "adds no `.env` setting" line, and `docs/guides/configuration.md`; check every `omrg web` option in the docs against `omrg web --help`.
- [x] 3.5 Add both operations and their schemas to `openapi.yaml` and the conformance families; document the setting in `docs/guides/web-workspace.md` and `src/omrg/transports/api/README.md`.
- [x] 3.6 Add `getUploadLimit`/`setUploadLimit` to `web/src/api/settings.ts`, `uploadLimitQuery` to `queries.ts` and `useSetUploadLimit` to `settingsMutations.ts` with its declared invalidation; test the paths and that a save refreshes the query.
- [x] 3.7 Build `UploadLimitPanel` in Settings › Workspace per design D4; test the limit in force, the default wording, the launch-set state with no form, a save, "Use the default", a value outside the reported range refused before any request, and a failed load with Retry.
- [x] 3.8 Make `UploadPanel` read `uploadLimitQuery`, state it, and refuse larger files locally; skip the local check when the limit is unknown. Test a 100 MiB server accepting a 60 MiB file, a 10 MiB server refusing a 12 MiB file without a request, a save in Settings reaching the panel without a reload, and an unreadable limit.
- [x] 3.9 Change the 413 text in `web/src/lib/errors.ts` to the limit-free wording; delete `MAX_UPLOAD_BYTES` and `UPLOAD_LIMIT_LABEL` from `web/src/lib/uploadLimit.ts`; add both names to the retired-name rule in `web/src/styles/noLegacyResidue.test.ts`; update the upload text in `docs/guides/web-workspace.md`.
- [x] 3.10 Check Settings › Workspace with the panel at 1280 px and 390 px in both themes; replace the 1280 px Settings screenshots in the guide; confirm no horizontal page scroll and a visible focus ring on the field and buttons.

## 4. Verification

- [x] 4.1 Run `uv run pytest -m "not slow"`, `uv run ruff check .`, `uv run lint-imports`, the OpenAPI validation, and `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` in `web/`; record exact results. Recorded 2026-10-15: web lint and typecheck clean, `npm test` 78 files and 816 tests passed, build passed; `ruff check .` passed; `ruff format --check` 619 files formatted; `lint-imports` 21 kept, 0 broken; OpenAPI valid; fast suite re-run in `./scripts/local_ci.sh` before the push.
- [x] 4.2 Run `openspec validate add-run-output-inspection-and-upload-limit --strict` and resolve every finding.
