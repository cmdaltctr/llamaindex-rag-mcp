---
name: omrs-design
description: Apply the OpenChamber-derived design system to the OMRS web workspace in web/. Use for styling, tokens, Tailwind and shadcn-style primitives, badges, icons, chat, studio, experiments, integrations, friendly errors, and visual verification of the redesign-web-workspace and add-web-ui-stack OpenSpec changes.
---

# OMRS design

Guide visual and layout changes to the OMRS web workspace in `web/`. The design source is OpenChamber's warm neutral palette, compact system-font UI, and flat tinted controls. Two OpenSpec changes carry the work:

- `add-web-ui-stack` adds Tailwind v4, the token bridge, and the first ten primitives. Apply it first.
- `redesign-web-workspace` rebuilds navigation and views on those primitives.

Both live in `openspec/changes/`. The spec deltas are the contract. This skill tells you how to meet them in a consistent visual style.

## Scope

The web app is a React 19 + Vite single-page app, tested with Vitest, linted with ESLint, and built with `npm`. It has no router library: views switch on `location.hash`. It has no i18n library: copy is plain British English in the source.

`web/src/styles/tokens.css` holds the palette. `web/src/styles/app.css` is the stylesheet entry and token bridge. These two are the only stylesheets: no hand-written view CSS and no `legacy` layer exist. Never write new hand-written CSS and never import a `.css` file from a component (`cascade.test.ts` and `noLegacyResidue.test.ts` fail if you do). `web/` has:

- Tailwind v4 through `@tailwindcss/vite`, CSS-first, no `tailwind.config` file.
- An `@theme inline` bridge that aliases utility names to the `tokens.css` variables. `tokens.css` stays the single source of truth.
- shadcn-style primitives in `web/src/components/ui/` (button, badge, card, dialog, input, select, label, tooltip, separator, table), built on Radix.
- `class-variance-authority`, `clsx`, `tailwind-merge` (the `cn()` helper), `lucide-react`, and `tw-animate-css`.

Check `web/package.json` and `web/src/components/ui/` before you rely on any of these. If they are absent, the stack change is not applied yet. Say so and stop. Do not hand-roll a replacement primitive. Add no dependency beyond the list in `add-web-ui-stack` plus `@tanstack/react-query`, which `redesign-web-workspace` adds (owner approval, 14 October 2026).

## Read by task

| Task | Read |
| --- | --- |
| Colours, typography, spacing, corners, borders, interaction states, contrast | [Visual foundations](references/foundations.md) |
| Buttons, badges, fields, dialogs, nav rows, icons, shadcn CLI use | [Component guidance](references/components.md), plus foundations |
| What a specific view contains and how it is laid out | [Screen guidance](references/screens.md) |
| Visible text, error and empty states, accessibility, right-to-left safety | [Copy and accessibility](references/copy-and-accessibility.md) |
| Any rendered UI change | [Verification](references/verification.md) before you start and before you report |

Paths in the references are relative to the repository root. The references hold a design snapshot. Read the current owning files before you edit.

`web/DESIGN.md` is the portable summary of this system in the Google DESIGN.md format, for tools that read that file. It mirrors `tokens.css` and this skill; it adds no rules. When you change a token, a primitive variant or a rule here, update `web/DESIGN.md` in the same change. `tokens.css` wins on any disagreement.

## Rules

1. Trace every change to a task in an OpenSpec `tasks.md`. If no task covers it, propose one first. Follow the Change Workflow in the repository `CLAUDE.md`.
2. Components read semantic tokens. Literal colours stay in `tokens.css`.
3. Reuse the primitives in `web/src/components/ui/`. Do not wrap them to override heights, radii, or colours. Change the primitive when the design changes.
4. Build only with primitives and Tailwind utilities. The old `.button`, `.control`, `.panel` and `.type-*` classes and their stylesheets are deleted by the redesign: never use them in new or rebuilt code, and delete the rules a rebuilt view no longer needs.
5. Behaviour stays unchanged unless a spec says otherwise. Keep save behaviour, API calls and destructive confirmations. Routes and stored UI state follow the redesign's design D9 and D12: the URL is the only source of location, and there are no redirects or migrations for earlier routes or keys.
6. Keep every file under 500 lines. Split by responsibility.
7. If the spec, design, and tasks disagree, report the conflict with numbered options. Do not pick one silently.

## Workflow

1. Name the change and task. Read its spec delta and `design.md`.
2. Confirm the stack is in place (see Scope).
3. Load the references in the table above. Read the owning files.
4. Build or restyle in the owning files. Write the test first for behaviour changes. Confirm it fails against the old code, then make it pass.
5. Run the checks and the visual matrix in the verification reference.
6. Report files changed, checks run with `PASS`, `FAIL`, `NOT RUN`, or `BLOCKED`, and anything unverified.

## Completion

Components use semantic tokens. Selection stays distinct from primary actions. Light and dark themes stay legible and meet WCAG AA. Every status carries text as well as colour. API failures show one friendly line and one action. Confirm each point with runtime evidence for each affected screen. A passing type check does not prove appearance.

## Decisions recorded on 14 October 2026

The owner settled four conflicts found when this skill was written. The OpenSpec files were updated to match.

1. Seven navigation areas: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings.
2. Icons come from `lucide-react`, not inline SVG. The licence is ISC.
3. The tinted button border is 30% light / 35% dark, as in `tokens.css`. `tokens.css` is authoritative over the design reference.
4. Badge text uses `--status-*-label` tokens (60% status colour, 40% text colour) because raw status colours fail AA. `add-web-ui-stack` defines them in `tokens.css` and tests the 4.5:1 ratios; use the `text-status-*-label` utilities. Do not use raw status colours as badge text.

## Discovery and attribution

Two copies exist: `~/.agents/skills/omrs-design/` (global; `~/.claude/skills` is a symlink to `~/.agents/skills`) and `.agents/skills/omrs-design/` in this repository, with `.claude/skills/omrs-design` linking to it. `.claude/` is gitignored, so that link stays local. Edit the repository copy first, then copy it over the global one so they do not drift. The skill is derived from `omms-design`, which is separate and keeps its own OMMS paths. Confirm discovery in the installed agent before you rely on automatic loading.

The design adapts OpenChamber's MIT-licensed material at revision `02306f32e4d191e4840440cbafa643ae899471c2`. The licence notice sits in `web/THIRD_PARTY_NOTICES.md`. Keep it when you copy material. `add-web-ui-stack` task 1.5 adds the notices for Radix, Tailwind, cva, clsx, tailwind-merge, lucide, and tw-animate-css.
