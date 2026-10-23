# Screen guidance

This file turns the `redesign-web-workspace` spec deltas into layout and styling decisions. The deltas stay the contract. Read the delta for the view you touch, then apply the design rules here. If they disagree, the delta wins. Report the disagreement.

## Card groups

These rules apply to every group of cards in any view.

- Cards of the same size: use a plain grid, `grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3`.
- Cards of different heights in one group: use the masonry layout. Settings > Providers is the example: the llama.cpp card holds a Local server panel and is much taller.
- For masonry, use the shared `MasonryColumns` component in `web/src/components/MasonryColumns.tsx`. It fits as many columns of at least 300px as the area allows, up to three. It puts each card in the shortest column, so a short card does not sit under a tall one. It places the cards again when the area or a card changes size. It does not move a card while focus is inside the cards, so a card that grows during an edit stays in its column. The cards move when focus leaves.
- Keep a tall card in one column at its full length. Do not make it span two columns. Do not put its content side by side to make it shorter.
- Put an extra panel under the card's fields. Separate it with `border-t border-border pt-3`.
- Do not use CSS columns (`columns-2`) for card groups. The order then reads down each column, and cards move to a different column when their height changes.
- Do not use native CSS masonry (`grid-lanes`) yet. Browser support is not ready.
- You can place a small fixed group by hand in column stacks when the order is important. Settings > MCP does this in `web/src/settings/McpSection.tsx`.

## Mini cards inside cards

Every card holds its parts in mini cards. Apply this rule in every view without being asked.

- Use `CardInset` from `web/src/components/ui/card.tsx` for one part of a card: one setting, one field, one read-only list, one status block, one drop zone.
- `CardInset` is lighter than the card: `rounded-control border border-border bg-background/60 p-3`, no shadow. It is the same pattern as the OMMS inner cards.
- Give each setting its own `CardInset`. Do not stack several settings in one.
- `SettingRow`, `KeySettingRow` (`web/src/settings/SettingRow.tsx`) and `ReadingSettingRow` already render a `CardInset`. Use them for a new setting, and do not wrap them again.
- Keep the card title, the card description, notices such as "Text you send leaves this machine" and the card's own action (for example Test) outside the mini cards.
- Never put a `Card` inside a `Card`. A section that brings its own cards (for example Knowledge Base > Add) sits outside the section card.
- A view with no cards at all is wrong. Put each panel of the view in a `Card`, then its parts in mini cards.
- When you apply this rule, check every tab of the view, not only the tab you were shown. `web/src/settings/SettingsCards.test.tsx` fails when a Settings tab has no card. Add a case there for a new tab.

## Shell

Navigation has seven items in this order: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings. Home is the landing view. Each row has a Lucide icon before its label and `aria-current="page"` on the active row.

| Element | Rule |
| --- | --- |
| Top bar | Muted surface, 1px bottom border, elevation shadow. Shows the brand, an engine status pill (collection count, or "offline"), the theme `Select` (System, Light, Dark), and an icon-only button beside it that shows sun or moon for the theme in effect and switches Light and Dark in one click. Its accessible name names the target theme. |
| Inspector | The global toggle and empty panel are gone. Detail regions open inside Chat, Studio, and Experiments on selection. |
| Skip link, main focus | Keep the existing skip link. Focus moves to the view `h1` after navigation. |
| Routes | Typed hash routes from `lib/routes.ts` (design D9): `#/home`, `#/knowledge-base[/<collection>]`, `#/chat[/<collection>]`, `#/studio[/<profile-id>[/<purpose>]]` (purpose is `ingest`, `search` or `answer`), `#/experiments`, `#/experiments/runs/<run-id>`, `#/integrations`, `#/settings`. Segments are URI-encoded. An unknown hash opens Home and is rewritten to `#/home`; earlier routes are not redirected. |
| Narrow screens | Below `md`, the navigation becomes one row of the seven area icons with short labels under the top bar (owner decision; no menu button). Targets are at least 44px. No horizontal page scroll. |

Read the presentation spec and `web/src/App.tsx` before you change route names.

## Home

A grid of project cards (`gap-3`, `items-start`). Each card is flat with a 1px border and shows the collection name (subsection title), a profile badge (hue hash), and document and chunk counts as meta text. The whole card opens the project.

Empty state: icon, one sentence naming the cause, one action that starts an ingest into a named collection.

A card opens `#/knowledge-base/<collection>`: source table with orphan status, upload panel, folder ingest panel, profile information, deletion, and search. Orphan status is a badge with text. The route is the active project; `lastCollection` in `omrs-preferences` is only the default for `#/knowledge-base` and `#/chat`.

## Chat

Layout: a centred transcript column at `min(100%, 48rem)`, the composer docked at the bottom of that column, and a right-hand knowledge base panel listing collections with counts and a selected state (`chip` or `--selection`, never the accent).

- Messages are plain rows with role labels. No bubble framework and no chat library.
- The view states that each question answers on its own. Put this notice near the composer in meta text.
- A "New chat" action clears the transcript. It keeps the selected knowledge base.
- Each assistant turn shows the answer, the verification status as text with its badge, citations as chips under the answer, and evidence in a collapsible section. Opening a chip or an evidence row shows the chunk in the shared chunk viewer.
- A failed turn shows one friendly line and a Retry action. The raw message goes to the console only.
- Switching the knowledge base mid-conversation keeps earlier turns. The next turn queries the new collection.
- The composer sends on a clear action. Disable it while a turn is pending, and keep the pending state visible as text.

Reuse `views/shared/ChunkViewer.tsx` (or its moved location). Delete `views/search/` and `views/ask/` only after chat tests cover their behaviour (task 3.5).

## Knowledge Base

Four sections, switched with `chip` buttons and shown one at a time: Sources, Search, Add, Profile (owner decision).

Manages the active project's sources: file upload (managed upload plus an ingest job), folder ingest from approved roots, and the source table.

- Sources, Search and Profile sit in one section card. Add shows two cards in `MasonryColumns`: Upload files and Ingest from an approved folder.
- Pick files with `FileDropZone` (`web/src/knowledge-base/FileDropZone.tsx`): drop files on the zone or press Choose files. Each pick adds to the list. Each listed file shows its size and a Remove button. The list clears when the upload run ends, and the results list replaces it.

- Show job status as text with a status badge.
- Refuse an oversized file in the client with a friendly message before any upload. Never send it.
- With no approved root, state that no folder is approved and name the `--root` server flag in a `code` element.
- Pick the active project with the same project switch used elsewhere. Do not add a second selector pattern.

## Studio

Gallery first: profile cards in two groups, "Built-in profiles" and "Your profiles", plus a "New empty profile" card. A closed "How profiles work" disclosure sits under the header. Each card shows the title, the profile ID, use and readiness, with Open profile, Duplicate and (for your profiles) Delete. Built-in profiles are read-only.

The canvas sub-page (`#/studio/<profile-id>/<purpose>`). The header shows the profile, an Ingest, Search and Answer switch and an "All profiles" link. A built-in profile shows a read-only notice and "Duplicate to edit". The panel sections are Pipeline settings (Base profile as text, Collection), Operations, Steps and connections, Connect ports, Revision and run, Step settings. "Save revision" asks "Save this revision?" when a collection uses the profile:

- The flow surface fills the main area.
- The operation palette is the right-hand column.
- Selecting a step opens its settings in a detail region on the same page.
- Revision, validation, and run behaviour are unchanged.

React Flow nodes and edges read the semantic tokens. Node kind badges use the hue hash. Run state on a node pairs the status colour with text. Respect `prefers-reduced-motion` for edge animation (`runs/useReducedMotion.ts` exists). The canvas needs a keyboard route to add, select, and delete nodes. Do not regress what `CanvasView` tests cover.

## Experiments

Folder groups, each listing its sub-experiments. An empty folder still shows with an empty indication. Provide forms to create a main folder and a sub-experiment with declared factors. A rejected path shows a validation message next to the field.

Keep the notebook panels intact: tool registration, trust notice, one-time credentials, and editor launch with a stop action. The one-time credential is shown once, so keep the copy action and the warning visible. Do not log or screenshot secrets.

A Runs section holds the run list, status filter, refresh, and run detail with evidence. Two sections keep this long view manageable. Use the existing filters.

With no experiment root approved, state it and name the `--experiment-root` server flag.

## Integrations

One card or table row per integration: chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web, and magika. Each shows name, one-line purpose, an availability badge with text (available or not installed), and the install command in a monospace block with a copy button.

State that availability reflects the running launch, and that installing needs the command run outside the app and the server restarted. The page never installs anything. A failed load shows the friendly line and Retry. Give the copy action visible confirmation and an announcement for assistive technology (a polite live region).

## Settings

Seven sections switched with `chip` buttons, one at a time (redesign design D13): Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace. Each chip writes `#/settings/<section>`. Controls that moved to other views are removed with their tests.

- Appearance: the same theme `Select` as the top bar.
- Providers: one card per registered LLM provider (Ollama, llama.cpp, OpenRouter, OpenAI-compatible, Anthropic; names come from the server) with read-only URLs and model names in `code`, role badges, "Installed" or an install hint, an address `Input` with source line, Save and Reset, a key `Input type="password"` (write-only, empties after save, Save key and Remove key), and a Test button that shows reachable or the reason as a status badge. An environment value shows "Set from environment (read-only here)" and locks the field. A config-file value shows "Set from config file (read-only here)" with the lock text "Set in ~/.config/omrs/omrs.jsonc. Edit that file and restart to change it." and locks the field. A key-file value shows "Set from key file (read-only here). Saving a key in the keychain overrides it." and keeps the key input. With no system keychain, one line replaces the key input and names the environment variable. Saved values apply at once, so show no restart banner. Show a key only as "Key set", its source, the save time and the last four characters when the server sends them. Never render a full key.
- Ollama card: add a number `Input` "Context window (tokens)" (2048 to 262144) with its source line and lock text; friendly error "Enter 2,048 to 262,144." for a bad value.
- Provider cards have different heights, so the section uses `MasonryColumns` (see Card groups). The llama.cpp card stays in one column. Its "Local server" panel sits under the provider fields after `border-t border-border pt-3`.
- llama.cpp card, "Local server" panel: state `Badge` with text (`stopped`, `starting`, `running`, `failed`) and one friendly line for each fixed reason (`binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout`, `not-configured`); `Input` fields for program path, model, context window and idle sleep with source lines, plus a one-line note on what idle sleep does; Start, Stop and Restart buttons (Start disabled while starting or running, Stop disabled while stopped); the line "omrs starts and stops only this server. It never touches a server you started yourself."; "Restart to apply" when saved values differ; program and model read-only without the `credentials` scope. Never show output of the server.
- Chat: a `Select` for the provider (items not ready are disabled with the reason), an `Input` for the model name, List models (fills a second `Select`), Test, Save and Clear. Say where the choice applies: MCP clients of this server without their own model, not metadata extraction, not stdio or the CLI. Show the cloud warning when the provider is cloud.
- MCP: the stdio client configuration (`uv run --directory <config_dir> omrs`) in a `code` block with a copy button, and, from `add-mcp-http-transport`: the HTTP on/off switch (show only the state the server returns), the HTTP configuration with the `/mcp` URL, token rotate and revoke with a new token shown once, and the saved web port with a next-launch notice.
- Server log: a monospace, terminal-style panel on the muted surface (`bg-muted`), one record per line (time, level badge, logger, message), level filter chips, Pause, Copy, and auto-scroll only while scrolled to the bottom. Mark it `role="log"` so screen readers announce new lines politely.
- Runtime and Workspace: capabilities and the workspace path. Keep paths in `code` elements with `overflow-wrap: anywhere`.
