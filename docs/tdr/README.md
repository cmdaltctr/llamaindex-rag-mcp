# Technical Decision Records (TDRs)

TDRs capture **implementation-level technical decisions** — platform-specific
workarounds, debugging findings, build pipeline decisions, and behavioural
fixes. For **architectural** decisions (framework choice, auth model, data
architecture), see the [ADR index](../adr/).

## When to write a TDR vs an ADR

| TDR                                                | ADR                                     |
| -------------------------------------------------- | --------------------------------------- |
| How to make a specific technology behave correctly | What stack/structure to use             |
| Platform-specific workarounds (WKWebView, sidecar) | Framework and language choices          |
| Debugging findings with root cause analysis        | Authentication and authorisation models |
| Build pipeline and tooling decisions               | Data model and API design               |
| "Why is X broken and how did we fix it?"           | "Why did we choose X over Y?"           |

## How to use

1. Copy `TEMPLATE.md` to a new file: `NNN-short-descriptive-title.md`
2. Fill in all sections — see the template for guidance
3. Add an entry to the table below
4. Commit with: `docs: add TDR-NNN <short title>`

## Index

| ID  | Title                                                                                                                           | Status   | Date       |
| --- | ------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------- |
| 001 | [Fix codebase map dead code and missing boundary validation](001-fix-codebase-map-dead-code-and-boundary.md)                    | Accepted | 2026-06-28 |
| 002 | [SonarCloud security gate via GitHub Actions](002-sonarcloud-security-gate-via-github-actions.md)                               | Accepted | 2026-06-28 |
| 003 | [Suppress Jupyter warning by installing ipywidgets as dev dependency](003-suppress-jupyter-warning-by-installing-ipywidgets.md) | Accepted | 2026-06-28 |
| 004 | [`--no-build` flag incompatible with editable installs in CI](004-uv-no-build-incompatible-with-editable-installs.md)           | Accepted | 2026-06-28 |

## Status values

- **Proposed** — under discussion, not yet agreed
- **Accepted** — agreed and active
- **Superseded** — replaced by a later TDR (link to superseding TDR)
- **Deprecated** — no longer relevant, not superseded by a specific TDR

Once a TDR is **Accepted**, never edit its decision — supersede it with a new
TDR and update the status here.
