# Component guidance

Read [visual foundations](foundations.md) first. Paths marked "planned" come from `add-web-ui-stack`. Confirm they exist before you import from them.

## Owners

| UI element | File |
| --- | --- |
| Primitives (button, badge, card, dialog, input, select, label, tooltip, separator, table) | `web/src/components/ui/<name>.tsx` (planned) |
| `cn()` helper (clsx + tailwind-merge) | `web/src/lib/` (planned, task 1.4) |
| shadcn CLI settings | `web/components.json` (planned; css path `src/styles/app.css`) |
| Tokens | `web/src/styles/tokens.css` |
| Layout, legacy controls, typography roles | `web/src/styles/app.css` |
| Views list and hash routing | `web/src/lib/views.ts`, `web/src/App.tsx` |
| Navigation | `web/src/components/AppNav.tsx` |
| Theme select | `web/src/components/ThemeSelect.tsx` |
| Dev proxy and test setup | `web/vite.config.ts`, `web/src/test/setup.ts` |

Imports in this project are relative (`../components/ui/button`). `tsconfig.json` defines no path alias. Do not add one inside a design change.

## Buttons

Variants (task 2.1): `default` (tinted primary), `destructive`, `outline`, `secondary`, `ghost`, `link`, and `chip` (selection). Heights: 36px default, 32px small, 24px extra-small. Read `button.tsx` for the exact size and icon-size keys the port kept.

- Primary is a tinted fill, not a solid accent fill. Label colour is `--accent-label`. Do not use `--accent` as text on its own tint.
- `chip` shows selection with `--selection`. It must not look like the primary action.
- A destructive button needs the same contrast check as the primary. Use the error label derived in the foundations contrast section.
- Set `type="button"` on every non-submit button inside a form.
- Do not keep the legacy `.button` classes on a migrated view.

```tsx
import { Plus } from "lucide-react";
import { Button } from "../components/ui/button";

export function NewPipelineAction({ onCreate }: { onCreate: () => void }) {
  return (
    <Button type="button" onClick={onCreate}>
      <Plus size={16} aria-hidden="true" />
      New pipeline
    </Button>
  );
}
```

An icon-only button needs an accessible name and a tooltip:

```tsx
<Button type="button" variant="ghost" size="icon" aria-label="Remove source" onClick={onRemove}>
  <Trash2 size={16} aria-hidden="true" />
</Button>
```

## Icons

Use `lucide-react`. Render at 16px, in `currentColor`, with `aria-hidden="true"` when text accompanies the icon. Empty states may use a larger size. Icon-only controls carry `aria-label`.

Task 1.2 lists these icons: home, message-circle, database, workflow, flask, plug, settings, upload, folder, search, x, play, trash, refresh, chevron-down. Export names change between Lucide releases (for example `House` and `Home`, `FlaskConical`). Check the installed version's exports before you import. Import named icons only, so the bundle tree-shakes.

Navigation row, following the existing `AppNav` pattern:

```tsx
<a className="app-nav__link" href="#/chat" aria-current={current === "chat" ? "page" : undefined}>
  <MessageCircle size={16} aria-hidden="true" />
  Chat
</a>
```

Keep `aria-current="page"` and the modified-click handling already in `AppNav`. Selected rows use `--selection` and normal text.

## Badges

Every category, type, or status label gets a colour. This is a standing rule. Do not ship a grey label and wait to be asked.

| Label | Treatment |
| --- | --- |
| Run status, answer status, integration availability | Status tokens: 10% fill, 1px border in the status colour, label colour from the contrast section. The value appears as text. |
| Collection profile (`documents`, `codebase`), node kind | Stable hue hash: transparent fill, `border-current`, text `oklch(0.42 0.13 <hue>)` in light and `oklch(0.8 0.13 <hue>)` in dark. |

One label has one hue everywhere. Use one shared hue function, owned beside the `Badge` primitive (task 1.3). If it does not exist yet, add it there once. Do not copy it into views. Unit-test the colour and text pairing. Colour never carries meaning alone.

## Inputs, selects, labels

Keep Radix behaviour. Fields have an elevated fill, a 1px `--border`, `--border-hover` on hover, 36px height, a 10px radius, and the shared focus outline. Every field has a visible `Label` bound by `htmlFor`. Validation messages sit next to the field and are tied to it with `aria-describedby`.

The Select primitive is Radix-based. The legacy `<select className="control control--select">` in `ThemeSelect.tsx` and `CollectionSelect` stays until its view migrates. Keep test queries working (`getByRole("combobox", { name })`). Radix Select renders differently from a native select in jsdom, so migrate the tests with the component.

## Dialogs

Use the Radix-based dialog. Keep focus trap, Escape to close, focus return to the trigger, and an accessible title (`DialogTitle`). Use an elevated background, a restrained shadow, and a capped width. The body scrolls when content is tall. Keep destructive confirmations as they are. Existing confirm flows (`ConfirmAction`, `usePreviewConfirm`) keep their behaviour when restyled.

The dialog close button needs an accessible name. Position it with logical properties (`end-4`, not `right-4`).

## Cards, table, separator

Cards are flat: 1px border, panel radius (12px), 16px padding, 12px between groups. No shadow. The table primitive is for source lists, runs, and integrations on wide screens. On narrow screens, wrap it in a horizontal scroller with a visible focus target, or restack rows. Do not let the page itself scroll sideways.

## Tooltip

Tooltips add detail. They never hold the only copy of important information. Do not hide helper text, warnings, or errors in a tooltip.

## shadcn CLI

`npx shadcn@latest add <component>` installs into `web/src/components/ui/`. It downloads from the network. Ask before you run it. After it runs:

1. Check that every class resolves against the bridge (see the bridge caution in foundations).
2. Replace default `ring-*` focus styles with the outline token.
3. Replace stock radii, heights, and colours with the OMRG geometry.
4. Confirm no existing view imports the new file unless a task says so.
5. Add its licence line to `web/THIRD_PARTY_NOTICES.md` if it adds a package.

## Error and empty states

One shared mapper turns fetch and HTTP failures into a friendly line plus one action (Retry, or guidance to start the server). Raw messages go to the console only. Never render parser output, status dumps, or stack text. An empty state has an icon, one sentence, and one action. See [copy and accessibility](copy-and-accessibility.md).
