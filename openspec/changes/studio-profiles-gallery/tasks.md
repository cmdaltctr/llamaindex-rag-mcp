# Tasks

Work in a feature worktree that forks from `integration/core-web` after `studio-canvas-layout` has merged and while `unify-profiles-and-pipelines` is ready to merge. Write each test first. Run it and confirm that it fails on the current code. Then write the code and confirm that the test passes. Load the `omrg-design` skill before you change any view. Web commands run in `web/`.

## 1. Profile API client and test fixtures

- [x] 1.1 Read the OpenAPI document of `unify-profiles-and-pipelines` (`src/omrg/transports/api/openapi.yaml`). Compare it with the API in proposal.md, including `standard_graphs` on the built-in profile detail (design D6). Confirm that only one active change modifies the `workspace-presentation` requirement "The URL is the only source of location" (design, Risks). Stop and report any difference before you continue.
- [x] 1.2 Write failing tests in a new `web/src/api/profiles.test.ts` for `listProfiles`, `getProfile` (with `standard_graphs` for a built-in), `createProfile`, `updateProfile` and `deleteProfile`: paths, bodies, encoded IDs, and a 409 refusal whose `used_by` is readable from `ApiError.body`.
- [x] 1.3 Create `web/src/api/profiles.ts` with the `ProfileRecord` type and the five calls. Verify that the 1.2 tests pass.
- [x] 1.4 Write a failing test in `web/src/api/pipelines.test.ts` that `saveRevision` returns `affected_collections`. Add the field to `saveRevision` (`web/src/api/pipelines.ts:248-260`). Verify that the test passes.
- [x] 1.5 Write failing tests in `web/src/api/mutations.test.tsx` that `useCreateProfile`, `useUpdateProfile`, `useDeleteProfile` and `useSaveRevision` invalidate `queryKeys.profiles()`. Add `profilesQuery`, `profileQuery` and the three mutations to `web/src/api/queries.ts` and `web/src/api/mutations.ts`. Verify that the tests pass.
- [x] 1.6 Add profile routes (`GET`, `POST`, `PATCH`, `DELETE`, `standard_graphs` for built-ins) and `affected_collections` on revision saves to `web/src/studio/test/fakeServer.ts`. Add a default `GET /v1/profiles` route to `web/src/test/fakeDocumentsServer.ts`. Add profile fixtures to `web/src/studio/test/helpers.ts`: `documents` and `codebase` built-ins, a user profile whose slots are the existing `p1` and `pnew` pipelines, and a not-ready user profile. Verify with `npm test -- src/api`.

## 2. Profile routes

- [x] 2.1 Write failing tests in `web/src/lib/routes.test.ts` for `#/studio`, `#/studio/<profile-id>`, `#/studio/<profile-id>/<purpose>` for each purpose, an unknown purpose that resolves to Home, URI-encoded IDs, and `formatRoute` for each form.
- [x] 2.1a Write failing tests in `web/src/lib/routes.test.ts` for `#/settings/<section>` with today's section ids from `web/src/settings/SettingsView.tsx`, `#/settings`, and the unknown section `#/settings/keys` (Home and `#/home`). Then add `{ area: "settings"; section }` to `web/src/lib/routes.ts` and make each Settings chip write its address. Verify with `npm test -- src/lib/routes.test.ts src/settings`.
- [x] 2.2 Change the studio route in `web/src/lib/routes.ts` to `{ area: "studio"; profileId; purpose }`. Change `web/src/App.tsx:18` to collapse the navigation on `route.profileId`. Update the studio hashes in `web/src/App.test.tsx` (lines 50, 231, 276, 300) and `web/src/App.failures.test.tsx` (lines 21 and 42). Verify with `npm test -- src/lib/routes.test.ts src/App`.

## 3. Studio header and profile gallery

- [x] 3.1 Write failing tests in `web/src/studio/StudioView.test.tsx` for the header sentences, the closed "How profiles work" disclosure and its four lines in order (spec "Studio explains what a profile is"). Import the strings from `profileCopy.ts`.
- [x] 3.2 Change the Studio `summary` in `web/src/lib/views.ts:20` and create `web/src/studio/profileCopy.ts`. Render the disclosure as a native `<details>`. Verify that the 3.1 tests pass.
- [x] 3.3 Replace the old gallery tests in `StudioView.test.tsx` with failing tests for the spec "Studio opens on a profile gallery": two sections, card title, grey ID, "Used by N collections", "Not used by any collection", built-in actions, "Not ready" badge with reasons, the empty "Your profiles" line, "Open profile" to `#/studio/<id>`, and a failed listing with Retry and an enabled "New empty profile" card. Assert that no "Templates", "Profile presets" or "Saved pipelines" section renders.
- [x] 3.4 Create `web/src/studio/ProfileCard.tsx` and `web/src/studio/ProfileGallery.tsx` on `GalleryCard`, `Badge`, `EmptyState` and `ErrorNotice`. Make `StudioView.tsx` render `ProfileGallery`. Verify that the 3.3 tests pass and that `StudioView.tsx` imports nothing from `drafts.ts`.
- [x] 3.5 Write failing tests for the spec "A new profile starts from a copy or from nothing": duplicate body, empty-profile body, navigation to `#/studio/<new-id>`, "Enter a title.", refusal keeps the dialog open, Cancel and Escape send nothing and return focus.
- [x] 3.6 Create `web/src/studio/NewProfileDialog.tsx` on the Radix `Dialog` primitive. Verify that the 3.5 tests pass.
- [x] 3.7 Write failing tests in a new `web/src/studio/ProfileTitleEditor.test.tsx` for the spec "User profiles can be renamed in place": PATCH body, trimmed title, empty title refused, Escape cancels, failure keeps the old title, focus returns to the pencil, no pencil on built-ins.
- [x] 3.8 Create `web/src/studio/ProfileTitleEditor.tsx` on the `DisplayNameEditor` pattern and use it on user profile cards. Verify that the 3.7 tests pass.
- [x] 3.9 Write failing tests for the spec "User profiles can be deleted when no collection uses them": one DELETE call, card removed, "Profile deleted.", disabled Delete with the visible reason, 409 message with `used_by`, Cancel returns focus.
- [x] 3.10 Create `web/src/studio/DeleteProfileDialog.tsx`. Verify that the 3.9 tests pass.
- [x] 3.11 Delete `web/src/studio/useStartPipeline.ts` and the presets, `templateDraft`, `blankDraft` and the `gridPositions` export from `web/src/studio/drafts.ts`. Remove their tests from `web/src/studio/drafts.test.ts` and keep the `initialDraft` tests. Search `web/src` for each removed name and verify that no caller remains.
- [x] 3.12 Remove `listTemplates`, `PipelineTemplate`, `pipelineTemplatesQuery`, `listPipelines`, `pipelinesQuery`, `createPipeline` and `useCreatePipeline` when 3.11 leaves them with no caller. Update `web/src/api/pipelines.test.ts`, `web/src/api/pipelineMutations.test.tsx` and `web/src/api/mutations.test.tsx`. Verify with `npm test -- src/api`.

## 4. Profile title as the only title

- [x] 4.1 Write failing tests in `web/src/studio/graph.test.ts` (line 71) and `web/src/studio/storage.test.ts`: `toLayout` returns no `title`, and a stored draft from an earlier version that holds `layout.title` loads without it. Update the `emptyDraft("…")` calls in `storage.test.ts` and `useDraft.test.ts`.
- [x] 4.2 Remove `title` from `DraftLayout`, `emptyDraft`, `fromDocument` and `toLayout`, remove `setTitle` (`web/src/studio/graph.ts`), and drop `title` in `asDraft` (`web/src/studio/storage.ts`). Verify that the 4.1 tests pass.
- [x] 4.3 Write a failing test in `web/src/studio/CanvasEditor.edit.test.tsx` that Pipeline settings shows "Base profile: documents" with no Title field and no profile list. It replaces the test "selects the graph profile and keeps collection inheritance by default" (line 206).
- [x] 4.4 Change `web/src/studio/PipelineBar.tsx` to show the base profile as text and keep the Collection field. Change the "Closing keeps work" case in `web/src/studio/CanvasPanel.test.tsx` to a collection edit. Verify that both tests pass.

## 5. "Step" in panel names (design D13)

- [x] 5.1 Change the expected titles in `web/src/studio/panelSections.test.ts` (lines 9 and 12) to "Steps and connections" and "Step settings". Add a case that no title contains "node".
- [x] 5.2 Change the section lookups to the new names: `web/src/studio/test/helpers.ts` (lines 11, 15 and 28); `web/src/studio/CanvasPanel.test.tsx` (lines 50, 70, 72, 74, 75, 160, 167, 168 and 169, including the rail button "Step settings, open"); `web/src/studio/CanvasEditor.edit.test.tsx` (lines 50, 136, 139 and 141); `web/src/studio/CanvasEditor.workspace.test.tsx` (lines 103, 167, 175 and 177).
- [x] 5.3 Change the inspector test strings: "Select a node to edit its settings" to "Select a step to edit its settings" (`CanvasEditor.edit.test.tsx:130`); "Remove node" to "Remove step" (`CanvasEditor.edit.test.tsx:153`, `CanvasEditor.settings.test.tsx:120`, `CanvasEditor.workspace.test.tsx:129`); "Bypass this node" to "Bypass this step" (`CanvasEditor.settings.test.tsx:84,86`).
- [x] 5.4 Run `npm test -- src/studio`. Confirm that the tests from 5.1 to 5.3 fail on the old names.
- [x] 5.5 Change the two titles in `web/src/studio/panelSections.ts` (lines 15 and 18). Keep the IDs `nodes` and `node-settings`, the icons and the order.
- [x] 5.6 Change the three strings in `web/src/studio/NodeInspector.tsx` (lines 31, 66 and 107). Run `npm test -- src/studio` and verify that it passes.
- [x] 5.7 Search `web/src` for `"Node settings"`, `"Nodes and connections"`, `"Remove node"`, `"Bypass this node"` and `"Select a node`. Verify that no user-facing string or test lookup remains. Code comments and code names may keep the word "node".

## 6. Canvas page with the profile header and purpose links

- [x] 6.1 Move the canvas tests to profile routes: change `openStudio("#/studio/p1" …)` and `"#/studio/pnew"` in `CanvasEditor.edit.test.tsx`, `CanvasEditor.settings.test.tsx`, `CanvasEditor.live.test.tsx` and `CanvasEditor.workspace.test.tsx` to the fixture profile routes from 1.6. Replace the "Open pipeline" link at `CanvasEditor.workspace.test.tsx:105` and the not-found test at `StudioView.test.tsx:151-155`. Run them and confirm that they fail.
- [x] 6.2 Write failing tests in a new `web/src/studio/ProfileHeader.test.tsx` for the spec "The canvas page shows the profile and its three pipelines": heading from the profile title, grey ID, kind badge, three links with `aria-current="page"` on the open one, Ingest when the route has no purpose, purpose line, a tab switch that keeps the unsaved draft, an unknown profile with "Back to Studio", an old pipeline ID such as `#/studio/pl_1` with the same not-found state and no change of address, and "All profiles".
- [x] 6.3 Create `web/src/studio/ProfileHeader.tsx`. Change `web/src/studio/CanvasPage.tsx` to load the profile, then the slot pipeline, as in design D2. Replace the heading at `CanvasEditor.tsx:100-102` and the "All pipelines" link at `CanvasEditor.tsx:105-110`. Change `StudioView.tsx:176-178` to pass `profileId` and `purpose`. Verify that the 6.1 and 6.2 tests pass.
- [x] 6.4 Add a test in `ProfileHeader.test.tsx` that renaming from the canvas header updates the heading and the gallery card. Use `ProfileTitleEditor` in the header and verify that the test passes.

## 7. Read-only built-in profiles

- [x] 7.1 Write failing tests in a new `web/src/studio/CanvasEditor.readonly.test.tsx` for the `pipeline-canvas` requirement "A read-only canvas shows a graph without changing it" and the `workspace-studio` requirement "Built-in profiles open read-only": the graph from `standard_graphs.search` of `documents`, disabled catalogue with "Read-only profile", disabled fields, no "Remove step", no save or Run buttons, Validate enabled, no drag, Delete key or connection, the read-only line in Connect ports, selection opens Step settings, no stored draft, the notice, "Duplicate to edit" and the Revision and run line.
- [x] 7.2 Write a failing test in `web/src/studio/useDraft.test.ts` for a `persist: false` option. Add the option to `web/src/studio/useDraft.ts` and verify that the test passes.
- [x] 7.3 Let `CanvasEditor` and `useCanvasSession` take a standard graph document with no pipeline. Add the `readOnly` flag to `CanvasEditor.tsx`, `FlowSurface.tsx`, `Palette.tsx`, `GraphOutline.tsx`, `ConnectionMenu.tsx`, `NodeInspector.tsx`, `ParamField.tsx` and `RunPanel.tsx` as listed in design D6. Add the notice and "Duplicate to edit" to `ProfileHeader.tsx`. Verify that the 7.1 tests pass.

## 8. Warning before a save

- [x] 8.1 Write failing tests in `web/src/studio/CanvasEditor.settings.test.tsx` for the spec "Saving a pipeline of a profile in use warns first": Search, Answer and Ingest wording, no dialog when unused, no request before confirm, Cancel keeps the draft, and the status line built from `affected_collections`. Keep the test "never changes a collection's profile when a layout or a revision is saved".
- [x] 8.2 Create `web/src/studio/SaveRevisionDialog.tsx`. Route "Save revision" through it in `useCanvasSession.ts` and `RunPanel.tsx`. Verify that the 8.1 tests pass.

## 9. Knowledge Base profile picker

- [x] 9.1 Write failing tests in `web/src/knowledge-base/KnowledgeBaseProfile.test.tsx` for the modified `local-web-workspace` requirement: two groups, title and ID on each option, a hidden not-ready profile with its line, a user profile ID in the preview body, a failed listing with Retry while the stored badge stays. Update `web/src/knowledge-base/KnowledgeBaseConfirm.test.tsx` to serve `GET /v1/profiles`.
- [x] 9.2 Change `Profile` to `string` in `web/src/api/documents.ts:203` and update `web/src/api/documents.test.ts`. Change `web/src/knowledge-base/ProfilePanel.tsx` to read `profilesQuery` and use `SelectGroup` and `SelectLabel`. Verify that the 9.1 tests pass.

## 10. Documentation

- [x] 10.1 Update `docs/guides/web-workspace.md`: the Studio row of the area table (line 320) with the new routes, a new "Profiles in Studio" section (built-in and your profiles, the three pipelines, duplicate, rename, delete, read-only, the save warning), the route in "Studio canvas layout" (line 344), its "Pipeline settings" item (line 348), and the Profile tab paragraph of "Database and profile in the Knowledge Base". Use ASD-STE100 style. Verify that no text calls the gallery "templates", "presets" or "saved pipelines".
- [x] 10.2 Change the section names in `docs/guides/web-workspace.md` (lines 350, 353, 355 and 393): "Nodes and connections" to "Steps and connections" and "Node settings" to "Step settings". Verify with `grep -n "Node settings\|Nodes and connections" docs/guides/web-workspace.md` that nothing remains.
- [x] 10.3 Re-capture `studio-gallery-light-1280.png`, `studio-gallery-dark-1280.png`, `studio-canvas-light-1280.png`, `studio-canvas-dark-1280.png`, `studio-canvas-light-390.png` and `studio-canvas-rail-light-1280.png` in `docs/guides/images/web-workspace/` by hand, with one built-in and one user profile. Open each file and verify that it shows the new header, gallery or profile header, and the new section names.
- [x] 10.4 Update `web/DESIGN.md` (line 213) and the Studio section and route row of `.agents/skills/omrg-design/references/screens.md`, including the section names, then copy that file over the global copy as the skill says. Verify that both copies match with `diff`.

## 11. Release coordination and verification

- [ ] 11.1 Confirm with the owner of `unify-profiles-and-pipelines` that both changes merge into the integration branch before the next release. Record the planned release in the pull request description. Verify that no release tag falls between the two merges.
- [x] 11.2 Run `npm test` in `web/` and verify that every test passes.
- [x] 11.3 Run `npm run typecheck` and `npm run lint` in `web/` and verify that both report no error.
- [x] 11.4 Search `web/src` for `layout.title`, `presetDraft`, `pipeline-templates`, `pipelineId` in studio routes, and hard-coded `"documents"` and `"codebase"` option lists. Verify that only test fixtures and the API layer remain.
- [x] 11.5 Run `wc -l` on every web file this change adds or edits and verify that none exceeds 500 lines. `tests/test_file_size_ceiling.py` checks Python files only.
- [x] 11.6 Run the visual matrix in the `omrg-design` verification reference for the gallery, a user profile canvas, a read-only built-in and the Knowledge Base Profile tab, in light and dark at 1280 px and 390 px. Record PASS or FAIL for each.
- [x] 11.7 Run `openspec validate studio-profiles-gallery --strict` after `studio-canvas-layout` is archived. Verify that it passes with no information line about a missing requirement.
