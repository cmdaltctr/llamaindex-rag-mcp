# Proposal

## Why

The backend change `unify-profiles-and-pipelines` makes the profile the one concept a collection follows: built-in profiles (`documents`, `codebase`) and user profiles, each with three pipelines (Ingest, Search, Answer). The Studio web page still shows the old model. It lists engine templates, two web-only "profile presets" and loose saved pipelines (`web/src/studio/StudioView.tsx:114-170`). The page summary says only "Build pipelines from templates and run them." (`web/src/lib/views.ts:20`). The user cannot see what a profile is, cannot rename or delete one, and a title typed on the canvas never reaches the gallery: the canvas writes `layout.title` (`web/src/studio/PipelineBar.tsx:21`), while the gallery reads `pipeline.title` (`web/src/studio/StudioView.tsx:84`). The Knowledge Base picker offers only the two built-in names (`web/src/knowledge-base/ProfilePanel.tsx:15`).

File references in this change point at the `feat/studio-canvas-layout` worktree, because that code merges first.

## What Changes

- The Studio header explains profiles in two short sentences. An optional "How profiles work" disclosure adds four plain lines.
- The gallery shows two sections: "Built-in profiles" (Open read-only, Duplicate) and "Your profiles" (rename with a pencil, grey profile ID, "Used by N collections", Open, Duplicate, Delete with confirmation, "Not ready" badge with reasons). A "New empty profile" card starts a profile with no steps.
- **BREAKING (web only)**: the "Templates", "Profile presets" and "Saved pipelines" sections go. The web-side preset logic goes: `presetDraft`, `templateDraft`, `blankDraft` (`web/src/studio/drafts.ts:9-50`), `useStartPipeline.ts`, and the hard-coded profile options of the canvas (`web/src/studio/PipelineBar.tsx:25-33`). Saved pipelines reach the user as user profiles through the backend migration.
- The canvas page of a profile shows the profile title as the page heading, its grey ID, and three purpose tabs (Ingest, Search, Answer). Each tab opens that purpose's pipeline on the existing canvas.
- The profile title is the only title. Renaming calls `PATCH /v1/profiles/{id}` from the gallery card or the canvas header. The canvas stops reading and writing `layout.title`. This fixes the rename bug.
- Built-in profiles open read-only, with a "Duplicate to edit" action. Each purpose tab shows the standard graph from the `standard_graphs` field of `GET /v1/profiles/{id}`.
- The canvas panel says "step" where users see "node": the section "Nodes and connections" becomes "Steps and connections", "Node settings" becomes "Step settings", and the inspector says "Select a step to edit its settings.", "Bypass this step" and "Remove step".
- Before the user saves a revision of a profile that collections use, a dialog names those collections. On the Ingest tab it adds that existing documents keep their old chunks until they are ingested again.
- The Knowledge Base profile picker lists ready built-in and user profiles in two groups. It hides profiles that are not ready and states why.
- **BREAKING (web only)**: the canvas route keys on the profile and the purpose: `#/studio/<profile-id>` (opens Ingest) and `#/studio/<profile-id>/<purpose>`, where purpose is `ingest`, `search` or `answer`. `#/studio` and `#/studio/<id>` keep working, with `<id>` now a profile ID. A saved link that names an old pipeline ID shows the not-found state with a link back to Studio. Built-in profiles have no slot pipelines (`slots` are `null` in `unify-profiles-and-pipelines`, spec `user-profiles`), so only a profile ID can address them.
- `docs/guides/web-workspace.md`, its Studio screenshots, `web/DESIGN.md` and the repository copy of the `omrg-design` screen guidance describe the new page.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-studio`: the pipeline gallery, the empty pipeline card and saved pipeline cards are replaced by a profile gallery with an explainer, duplicate, rename and delete. New requirements cover the profile canvas page with purpose tabs, read-only built-in profiles and the warning before a save. Three requirements change their `studio-canvas-layout` text: the canvas sub-page uses the profile route, its slim bar shows the profile header and an "All profiles" link, the Pipeline settings section loses its Title and Profile fields, and the sections "Nodes and connections" and "Node settings" become "Steps and connections" and "Step settings" in the panel and on the icon rail.
- `workspace-presentation`: the Studio routes in "The URL is the only source of location" change to `#/studio/<profile-id>` and `#/studio/<profile-id>/<purpose>`. The route examples in "Navigation follows the seven-area structure" and in "The navigation collapses on the canvas sub-page" (added by `studio-canvas-layout`) follow.
- `local-web-workspace`: the requirement "The Profile tab shows the stored profile truthfully" changes its selectable set from `documents` and `codebase` to every ready built-in or user profile, in two groups, with not-ready profiles hidden and explained. The Knowledge Base picker requirement lives here, so `workspace-projects` needs no delta (design D9).
- `pipeline-canvas`: one ADDED requirement for a read-only canvas. No existing requirement changes, because `clarify-canvas-steps` owns this capability.

## Impact

- **Code (web only):** `web/src/lib/views.ts`, `web/src/lib/routes.ts`, `web/src/App.tsx` (canvas route check, `App.tsx:18`), `web/src/studio/` (`StudioView.tsx`, `CanvasPage.tsx`, `CanvasEditor.tsx`, `useCanvasSession.ts`, `PipelineBar.tsx`, `RunPanel.tsx`, `Palette.tsx`, `GraphOutline.tsx`, `ConnectionMenu.tsx`, `FlowSurface.tsx`, `NodeInspector.tsx`, `ParamField.tsx`, `panelSections.ts`, `graph.ts`, `drafts.ts`, `GalleryCard.tsx`, new profile components), `web/src/knowledge-base/ProfilePanel.tsx`, `web/src/api/` (new `profiles.ts`; `documents.ts`, `pipelines.ts`, `queries.ts`, `mutations.ts`).
- **API used (from `unify-profiles-and-pipelines`):** `GET /v1/profiles`, `POST /v1/profiles`, `GET`, `PATCH` and `DELETE /v1/profiles/{id}`, the `standard_graphs` field of `GET /v1/profiles/{id}` for a built-in, the `affected_collections` field of `POST /v1/pipelines/{pipeline_id}/revisions`, and `PATCH /v1/collections/{collection}/profile` with any ready profile ID. The web stops calling `GET /v1/pipeline-templates`, `GET /v1/pipelines` and `POST /v1/pipelines`.
- **Dependencies:** `studio-canvas-layout` must merge and archive first. Four MODIFIED blocks copy its requirement text. This change lands after `organise-backend-folders`, so backend paths it cites use `src/omrg/transports/api/routes/`. No new package.
- **Release:** this change and `unify-profiles-and-pipelines` ship in the same release. The old gallery calls `POST /v1/pipelines`, which answers 410 after the backend change. Do not cut a release between the two merges.
- **Tests:** Vitest and Testing Library, test-first. Existing files that change are listed in `tasks.md`.
- **Docs:** `docs/guides/web-workspace.md`, screenshots in `docs/guides/images/web-workspace/`, `web/DESIGN.md`, `.agents/skills/omrg-design/references/screens.md`.
- **Not affected:** Python code, stored data, MCP and CLI. This change edits no OpenAPI text; the `standard_graphs` field belongs to `unify-profiles-and-pipelines`.
