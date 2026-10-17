# Design

## Context

See proposal.md for the reasons. This section lists only the facts that shape the approach. Web paths point at the `feat/studio-canvas-layout` worktree, because that code merges before this change.

- The gallery is one component, `Gallery` in `web/src/studio/StudioView.tsx:96-173`. It reads three queries: templates, pipelines and collections (`StudioView.tsx:98-100`).
- Cards come from `GalleryCard` (`web/src/studio/GalleryCard.tsx:16-31`): a `Card` with `role="group"` named by its title. Tests find cards by that group name (`StudioView.test.tsx:17-18`).
- A new pipeline is made in the browser: `useStartPipeline` posts `{title, layout: {title}}` and writes the seeded draft to browser storage (`web/src/studio/useStartPipeline.ts:17-27`). The presets live only in the web (`web/src/studio/drafts.ts:9-50`).
- The rename bug: the Title field writes `layout.title` (`PipelineBar.tsx:21`, `graph.ts:246`). The canvas heading reads `draft.layout.title || pipeline.title` (`CanvasEditor.tsx:101`). The gallery reads `pipeline.title` (`StudioView.tsx:84`). No API call renames a pipeline.
- The canvas route is `#/studio/<pipeline-id>` (`web/src/lib/routes.ts:46-51,78`). `CanvasPage` loads one pipeline and mounts `CanvasEditor` with `key={pipelineId}` (`CanvasPage.tsx:14-40`). Drafts are stored per pipeline ID (`useDraft.ts:12-29`, `storage.ts:49-62`).
- The canvas panel has six sections; Pipeline settings holds Title, Profile and Collection (`panelSections.ts:12-19`, `PipelineBar.tsx:15-47`). The Profile list is hard-coded to `documents` and `codebase` (`PipelineBar.tsx:30-32`). Two section titles use the word "node": "Nodes and connections" and "Node settings" (`panelSections.ts:15,18`). The inspector also says "Select a node to edit its settings.", "Bypass this node" and "Remove node" (`NodeInspector.tsx:31,66,107`).
- Tests find panel regions and section buttons by these titles: `test/helpers.ts:11,15,28`, `panelSections.test.ts:9,12`, `CanvasPanel.test.tsx:50,70,72,74,75,160,167,168,169`, `CanvasEditor.edit.test.tsx:50,129,130,136,139,141,153`, `CanvasEditor.workspace.test.tsx:103,129,167,175,177` and `CanvasEditor.settings.test.tsx:84,86,120`.
- The Knowledge Base picker is `ProfilePanel` (`web/src/knowledge-base/ProfilePanel.tsx:15-78`). `Profile` is the union `"documents" | "codebase"` (`web/src/api/documents.ts:203`). The `Select` primitive already exports `SelectGroup` and `SelectLabel` (`web/src/components/ui/select.tsx:7,62`).
- Patterns to reuse: the pencil editor with a grey name under the title (`knowledge-base/DisplayNameEditor.tsx:17-119`), the Radix dialog in `knowledge-base/DeleteDialog.tsx`, `EmptyState`, `ErrorNotice`, and the `Badge` variants `hue`, `neutral` and status (`components/ui/badge.tsx:12-24`).
- `unify-profiles-and-pipelines` (spec `user-profiles`) says: built-in profiles return `slots` with three `null` values; a duplicate of a built-in gets "the standard ingestion, search and answer graphs, shaped by that built-in's settings"; `GET /v1/profiles/{id}` of a built-in returns `standard_graphs: {ingest, search, answer}`, and list items do not carry it; `getPipeline` gains `profile_slot`; `POST /v1/pipelines` returns 410 Gone. Its upgrade step titles each migrated profile with a non-empty `layout.title`, else `pipeline.title`. Its proposal says both changes ship in the same release.
- `GET /v1/pipeline-templates` shapes its graphs from the host's hybrid and reranker settings (`src/omrg/compose_pipelines.py:198-222`), not from a profile. So it cannot show what `codebase` runs when the host default differs.

## Goals / Non-Goals

**Goals:**

- One place in the web knows the profile API: a new `web/src/api/profiles.ts`.
- The profile title has one source (the profile record) and one write path (`PATCH /v1/profiles/{id}`).
- The existing canvas, panel and run behaviour stay as they are, apart from the read-only mode and the save warning.

**Non-Goals:**

- No change to step cards, step names or the content of step settings. `clarify-canvas-steps` owns them. This change renames only the panel sections and the three inspector strings that say "node" (D13).
- No editing of a profile description. The API accepts `description` in `PATCH`, but nobody asked for it. The card shows it read-only.
- No change to Home cards or the Knowledge Base summary badge. They keep the stored profile ID.
- No Python, OpenAPI or stored-data change in this change. One API addition is requested from `unify-profiles-and-pipelines` (D6).

## Decisions

### D1. The canvas route keys on the profile and the purpose

Routes: `#/studio`, `#/studio/<profile-id>` (opens Ingest) and `#/studio/<profile-id>/<purpose>` with purpose `ingest`, `search` or `answer`. Any other purpose resolves to Home, as other unknown routes do (`routes.ts:28-61`). The route model becomes `{ area: "studio"; profileId: string | null; purpose: Purpose | null }`. The purpose links are plain hash anchors, so a tab switch adds a history entry and Back returns to the previous tab.

Why: built-in profiles have no slot pipelines (`slots` are `null`), so a pipeline ID cannot address them. The address bar also names the concept the user works with. `#/studio/<id>` keeps working, with `<id>` now a profile ID.

Cost: the route list in `workspace-presentation`, one scenario there, and the navigation rule that `studio-canvas-layout` adds all name `#/studio/<pipeline-id>`. This change modifies those three requirements. This change also carries `#/settings/<section>` and its scenario for `add-llm-provider-settings`, so only one change modifies "The URL is the only source of location" (see Risks). `App.tsx:18` decides the collapsed navigation from `route.pipelineId`; it changes to `route.profileId`.

Saved links to an old pipeline ID show the not-found state with "Back to Studio", which opens the gallery. The redesign forbids redirects for earlier routes (redesign design D9, restated in the `omrg-design` skill rule 5). The spec scenario "Unknown profile" covers this case: `#/studio/pl_1` names an old pipeline ID.

Alternatives:

1. Keep `#/studio/<pipeline-id>` and link the tabs to slot pipeline IDs. No route change and old links work, but built-in profiles cannot open. Rejected.
2. Resolve an old pipeline ID through `profile_slot` and replace the hash. Friendlier for old links, but a redirect. Rejected: it needs an owner exception to the no-redirect rule, and the migrated profile is easy to find in the gallery under its old title.

Default purpose: Ingest, because it comes first in Ingest, Search, Answer. Alternative: Search, the slot people edit most. Rejected to keep "first tab opens first".

### D2. The canvas page loads the profile, then the slot

`CanvasPage` reads `profileQuery(profileId)`. A 404 shows `NotFound` for "profile". For a user profile it reads `pipelineQuery(slots[purpose])` and mounts `CanvasEditor` with `key={pipelineId}`, so drafts stay keyed by pipeline ID and a tab switch keeps unsaved edits with no new code. For a built-in profile it mounts `CanvasEditor` read-only on the standard graph of that purpose (D6).

### D3. The profile title is the only title

- Remove `title` from `DraftLayout`, `emptyDraft`, `fromDocument`, `toLayout` and remove `setTitle` (`graph.ts:34,47-50,73,93,116-117,246-247`). `asDraft` in `storage.ts` drops a `title` key from drafts stored by earlier versions.
- Remove the Title field from `PipelineBar`.
- The canvas heading shows `profile.title`.
- A new `useUpdateProfile(profileId)` mutation sends `PATCH /v1/profiles/{id}` and invalidates `queryKeys.profiles()`, so the gallery and the canvas heading show the new title at once.
- A new `ProfileTitleEditor` follows the `DisplayNameEditor` pattern: pencil, inline field, Enter saves, Escape cancels, focus returns to the pencil, grey ID line ("Profile ID: papers-search"). It refuses an empty title on the client ("Enter a title.").

Alternative: keep writing `layout.title` and copy it into the profile. Rejected: two sources caused the bug.

### D4. Creating asks for the title first

The server makes `profile_id` from the title and the ID never changes (`user-profiles`, "A user profile has a fixed id and three pipelines"). So "Duplicate" and "New empty profile" open one `NewProfileDialog` with a title field before any request. Duplicate proposes "<source title> copy". "Create profile" sends `POST /v1/profiles {source, title}`. On success the page navigates to `#/studio/<new-profile-id>`. The web no longer seeds drafts; the server copies the graphs.

Alternative: create with a default title and rename later. Rejected: the ID would keep the default name for ever.

### D5. Delete is guarded twice

The card disables "Delete" while `used_by` is not empty and says why in visible text (a tooltip must never hold the only copy, per the `omrg-design` component guidance). The server can still refuse with 409 if a collection picked the profile after the list loaded; the dialog then shows the names from the 409 `used_by` body and keeps the card. `ApiError.body` already carries the parsed body (`web/src/api/client.ts:28-29,146`).

### D6. Built-in profiles: standard graphs on a read-only canvas

Data: `unify-profiles-and-pipelines` (design D23, requirement "Reading a built-in profile returns its standard graphs") gives one field. `GET /v1/profiles/{id}` of a built-in returns `standard_graphs: {ingest, search, answer}`, each a graph document, the same graphs that `POST /v1/profiles` copies into a duplicate. List items do not carry it, so `CanvasPage` reads the detail. The web never shapes these graphs itself, so no preset logic comes back.

Behaviour: `CanvasPage` sets `readOnly` for a built-in. `CanvasEditor` takes a graph source (a pipeline with its revision, or a standard graph document with no pipeline) and passes `readOnly` down:

| Part | Read-only behaviour |
| --- | --- |
| `useDraft` | New `persist: false` option: changes stay in memory, nothing is written to storage. Selection and viewport still work. |
| `useCanvasSession` | No runs query (no pipeline ID). Validate sends the document. |
| `FlowSurface` | `nodesDraggable`, `nodesConnectable` and the Delete key handler are off. Selection stays on. |
| `Palette` | Every operation disabled with the reason "Read-only profile". |
| `GraphOutline` | No Remove buttons. |
| `ConnectionMenu` | Replaced by the line "This pipeline is read-only." |
| `NodeInspector`, `ParamField` | Fields and checkboxes disabled; no "Remove step" button. |
| `RunPanel` | No "Save layout", "Save revision" or "Run". Validate stays, with "Duplicate this profile to save and run its pipelines." |

Spec placement: the canvas behaviour is an ADDED requirement in `pipeline-canvas`, which `clarify-canvas-steps` owns. The built-in context (notice, "Duplicate to edit", no run) sits in `workspace-studio`.

Alternatives:

1. Show `GET /v1/pipeline-templates` with `graph.profile` set to the built-in. Rejected: those graphs follow the host settings, so the `codebase` view could miss its hybrid steps.
2. Offer only "Duplicate" on built-ins. Rejected: the user asked for "Open read-only".
3. A separate read-only viewer component. Rejected: it would copy the surface and the panel and drift from them.

### D7. The save warning reads `used_by`, the status reads `affected_collections`

Before `saveRevision`, `CanvasEditor` checks `profile.used_by`. When it is not empty, a `SaveRevisionDialog` opens with purpose-specific text (wording in the spec). After the save, the status line uses `affected_collections` from the response, which is authoritative. `saveRevision` (`web/src/api/pipelines.ts:248-260`) returns that field as well. `useSaveRevision` also invalidates `queryKeys.profiles()`.

Alternative: save first and warn after. Rejected: the brief (D4) asks for a warning before saving.

### D8. Pipeline settings show the base profile, not a choice

The backend sets `graph.profile` of every slot graph to the profile's `base_profile` ("Each graph SHALL name the base profile as its operational profile"). A choice on the canvas would let the user break that. So `PipelineBar` shows "Base profile: documents" as text and keeps only the Collection field. The Pipeline settings section keeps its ID, title, icon and position.

The `pipeline-canvas` requirement "Node controls show effective behaviour" said "Profile selection SHALL support documents/codebase or collection inheritance". `clarify-canvas-steps` owns that requirement and rewords the sentence to match `unify-profiles-and-pipelines` D8: each pipeline inherits settings from its profile's base profile, and a step setting overrides the inherited value. This change needs no delta for it.

### D9. The Knowledge Base picker uses select groups

`ProfilePanel` reads `profilesQuery`. Ready built-ins go in a `SelectGroup` labelled "Built-in profiles"; ready user profiles in one labelled "Your profiles". Each option shows the title and the ID in `font-mono` muted text. Not-ready profiles become one line each under the list. `Profile` in `documents.ts` becomes `string`, and `changeProfile` and `useChangeProfile` take any ID.

The requirement that governs this list, "The Profile tab shows the stored profile truthfully", lives in `local-web-workspace`, not in `workspace-projects`. This change modifies it there, because its scenario "not `documents` or `codebase`" becomes wrong. No other change in this batch touches `local-web-workspace`. `workspace-projects` holds no profile picker requirement, so it gets no delta.

### D10. Explainer copy lives in one file

`web/src/lib/views.ts` gets the new two-sentence summary for Studio. A new `web/src/studio/profileCopy.ts` holds the four disclosure lines, the three purpose lines and the warning sentences, so tests import the same strings. The disclosure is a native `<details>` with a `<summary>`, as `RunPanel.tsx:54-57` already uses. No new primitive.

### D11. Files and removals

New files: `web/src/api/profiles.ts` (+ test), `web/src/studio/ProfileGallery.tsx`, `ProfileCard.tsx`, `ProfileTitleEditor.tsx`, `NewProfileDialog.tsx`, `DeleteProfileDialog.tsx`, `ProfileHeader.tsx` (title, badges, purpose links, read-only notice), `SaveRevisionDialog.tsx`, `profileCopy.ts`. Each stays far under 500 lines.

Removed when no caller is left (search before you delete): `presetDraft`, `presetTitle`, `PRESET_PROFILES`, `templateDraft`, `blankDraft` and the `gridPositions` export (`drafts.ts`), `useStartPipeline.ts`, `listTemplates` and `PipelineTemplate` (`pipelines.ts:283-294`), `pipelineTemplatesQuery`, `pipelinesQuery` and `listPipelines`, `createPipeline` and `useCreatePipeline`. `initialDraft` stays.

### D12. Spec ownership and archive order

- `workspace-studio`: owned by this change. Three requirements are removed and replaced. Three requirements carry `studio-canvas-layout` text and are modified with it whole, including the section renames of D13: "The canvas sub-page gives the graph the full width", "The canvas panel groups the controls in icon accordion sections" and "The canvas panel collapses to an icon rail". Scenario titles stay as they are, because archive matches scenarios by title; only their bodies say "step".
- `workspace-presentation`: two baseline requirements and one requirement that `studio-canvas-layout` adds are modified (D1).
- `local-web-workspace`: one MODIFIED requirement (D9).
- `pipeline-canvas`: one ADDED requirement only (D6).

Archive this change after `studio-canvas-layout`. Until then `openspec validate --strict` passes but prints that archive would not find "The canvas panel groups the controls in icon accordion sections", "The canvas panel collapses to an icon rail" and "The navigation collapses on the canvas sub-page".

### D13. "Step" replaces "node" in panel names

The canvas shows steps to the user, and `clarify-canvas-steps` calls each card a step. Two panel sections still say "node". This change renames them, because it owns `workspace-studio`, where the section names live:

| Old text | New text | Where |
| --- | --- | --- |
| "Nodes and connections" | "Steps and connections" | `panelSections.ts:15` (section title and region name) |
| "Node settings" | "Step settings" | `panelSections.ts:18` (section title, region name and rail button) |
| "Select a node to edit its settings." | "Select a step to edit its settings." | `NodeInspector.tsx:31` |
| "Bypass this node" | "Bypass this step" | `NodeInspector.tsx:66` |
| "Remove node" | "Remove step" | `NodeInspector.tsx:107` |

The section IDs (`nodes`, `node-settings`), icons and order stay the same, so stored open-section state and the rail keep working. Code names (`NodeInspector`, `nodeId`) stay. The rename changes only text users see and the test lookups in Context. The `clarify-canvas-steps` intro line and Details area use the new names.

- Alternative: leave the rename to `clarify-canvas-steps`. Rejected: that change does not own `workspace-studio`, and two changes must not modify the same requirement.
- Alternative: also rename the section IDs. Rejected: no user sees them, and stored state would reset.

### D14. Release

This change ships in the same release as `unify-profiles-and-pipelines`. The old gallery calls `POST /v1/pipelines`, which answers 410 after the backend change, and this gallery calls `/v1/profiles`, which does not exist before it. The web paths do not move in `organise-backend-folders`; that change moves only backend files. It lands first, so backend paths that this change cites use `transports/api/routes/`.

## Risks / Trade-offs

- [The profile API can still change before apply] → Keep every call in `api/profiles.ts`. Task 1.1 re-reads the backend OpenAPI before code starts and stops on any difference.
- [Titles typed on the canvas before this change live only in `layout.title`] → The backend upgrade step titles each migrated profile with a non-empty `layout.title` (`unify-profiles-and-pipelines` D10), so the gallery shows the name the user typed.
- [Old `#/studio/<pipeline-id>` bookmarks show not found] → The page offers "Back to Studio", where the migrated profile is listed under its canvas title.
- [`used_by` can be stale when the save dialog opens] → The status line after the save names the server's `affected_collections`. The canvas page refetches the profile on mount.
- [Stored drafts from earlier versions hold `layout.title`] → `asDraft` drops it. A test covers an old stored draft.
- [Tests and docs find sections by name] → Task group 5 changes every lookup listed in Context in one step, and `panelSections.test.ts` pins the new titles.
- [`add-llm-provider-settings` needs `#/settings/<section>`] → Resolved: this change holds both route edits (the profile routes and `#/settings/<section>`). `add-llm-provider-settings` has no `workspace-presentation` delta and lands after this change. This change adds `#/settings/<section>` to the router for today's Settings sections, so the spec it archives is true. `add-llm-provider-settings` then adds its new sections (Providers, Chat) to the same list.

## Migration Plan

1. Merge and archive `studio-canvas-layout`.
2. Land `organise-backend-folders`.
3. Merge `unify-profiles-and-pipelines` (it migrates saved pipelines into user profiles) and this change in the same release (D14).

Rollback: revert both changes together, because `POST /v1/pipelines` returns 410 after the backend change and the old gallery depends on it.

## Open Questions

None. The earlier questions are closed: the `pipeline-canvas` profile sentence is reworded by `clarify-canvas-steps` (D8); the backend upgrade step takes a non-empty `layout.title` (`unify-profiles-and-pipelines` D10); old pipeline links show not found with a link back to the gallery, with no redirect (D1).
