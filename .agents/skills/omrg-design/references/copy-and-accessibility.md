# Copy and accessibility

## Copy

The web app has no i18n library. Visible text is English strings in the source (`views.ts`, components). Do not add a translation system inside a design change.

- Write British English: colour, organise, licence (noun), behaviour, catalogue.
- Follow the repository's writing rule: plain words, active voice, one idea per sentence, procedures in 20 words or fewer, no unexplained abbreviations.
- Keep product names, commands, flags, model identifiers, and paths literal. Put them in `code` elements.
- Button labels name the action: "Upload file", "Start ingest", "Copy command". Avoid "OK" and "Submit".
- Keep wording consistent across views. The same thing has the same name everywhere ("knowledge base", "project", "collection": a project is a collection, so use the term the spec uses for that view).

## Errors, empty states, notices

One shared mapper turns a failure into a short line that names what failed, plus one action. Examples of the shape:

- "Could not load collections. Check that the OMRG server is running." with a Retry button.
- "No folder is approved. Start the server with `--root <folder>`."

Rules:

1. Never render parser output, JSON errors, status dumps, or stack text. Log the raw message to the console.
2. One action per message. Retry for transient failures. Guidance for configuration failures.
3. An empty state has an icon, one sentence that names the cause, and one action.
4. Use `role="status"` (polite) for loading and success messages. Use `role="alert"` for errors that need attention now. Do not announce the same message twice.
5. Keep the standing notices the spec requires: "each question answers on its own" in Chat, the availability notice in Integrations, the trust notice in Experiments.

Test the mapper: assert that a parser message such as `Unexpected token <` never reaches the DOM.

## Accessibility baseline

Radix gives dialogs, selects, and tooltips their keyboard and aria behaviour. Do not strip it.

1. Every control has an accessible name. Icon-only buttons use `aria-label`. Decorative icons use `aria-hidden="true"`.
2. One `h1` per view, with ordered headings below it. Focus moves to the `h1` (`tabIndex={-1}`) after navigation. Keep the existing pattern.
3. Visible focus on every interactive element: 2px outline in `--focus-ring`, 2px offset. Never remove it without an equal replacement.
4. Text meets WCAG AA: 4.5:1 normal, 3:1 large text and UI boundaries. See the contrast table in foundations.
5. Colour is never the only signal. Status badges state the value in text. Selected rows use a fill and `aria-current` or `aria-pressed`.
6. Dialogs trap focus, close on Escape, and return focus to the trigger.
7. Lists of results use list or table semantics. A table has header cells and a caption or accessible name.
8. Copy actions confirm in text and announce through a live region.
9. Honour `prefers-reduced-motion`. Keep transitions to opacity, colour, and transform.
10. Touch targets reach 44px on narrow screens. Controls keep 36px on desktop.

## Right-to-left safety

The English UI is the only language, but `app.css` uses logical properties only, so a right-to-left document mirrors without extra rules. Keep that property. In new code use logical Tailwind utilities (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `border-s`, `border-e`, `text-start`). Do not add physical `left`, `right`, `ml-*`, `mr-*`, `pl-*`, `pr-*`, or `text-left`. Mirror directional chevrons only if you add right-to-left support later. Put `min-w-0` on shrinking flex and grid children, and let labels wrap.
