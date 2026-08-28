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
| 002 | [SonarCloud security gate via GitHub Actions](002-sonarcloud-security-gate-via-github-actions.md)                               | Superseded by [TDR-007](007-ci-quality-toolchain-consolidation.md) | 2026-06-28 |
| 003 | [Suppress Jupyter warning by installing ipywidgets as dev dependency](003-suppress-jupyter-warning-by-installing-ipywidgets.md) | Accepted | 2026-06-28 |
| 004 | [`--no-build` flag incompatible with editable installs in CI](004-uv-no-build-incompatible-with-editable-installs.md)           | Accepted | 2026-06-28 |
| 005 | [fetch_k override parameter for experiment pool-size sweeps](005-fetch-k-override-for-experiment-pool-sweeps.md)                | Accepted | 2026-06-29 |
| 006 | [OpenRouter structured outputs are per-endpoint, so `require_parameters` needs a downgrade path](006-openrouter-structured-outputs-per-endpoint.md) | Accepted | 2026-08-07 |
| 007 | [CI quality toolchain consolidation — Ruff, CodeRabbit, Codecov](007-ci-quality-toolchain-consolidation.md)                        | Accepted | 2026-08-10 |
| 008 | [Copy uv cache files for NLTK Pathsec in Linux CI](008-copy-uv-cache-files-for-nltk-pathsec.md)                                    | Accepted | 2026-08-13 |
| 009 | [Dead TYPE_CHECKING imports in provider modules](009-dead-type-checking-imports-in-provider-modules.md)                            | Accepted | 2026-08-13 |
| 010 | [Separate code chunking units and make metadata budget node-exact](010-separate-code-chunking-units-and-metadata-budget.md)        | Accepted | 2026-08-18 |
| 011 | [Pre-calibration audit and executable experiment-plan validation](011-pre-calibration-audit-and-experiment-plan-validation.md)     | Accepted | 2026-08-18 |
| 012 | [Widen Null-typed LanceDB adapter columns before write](012-widen-null-typed-lancedb-adapter-columns.md)                               | Accepted | 2026-08-19 |
| 013 | [Narrow the ingestion write lock to the mutation section](013-narrow-ingestion-write-lock-to-mutation-section.md)                      | Accepted | 2026-08-19 |
| 014 | [Experiment-validity framework: runtime manifests, preflight aborts, and cell agreement](014-experiment-validity-framework.md)            | Accepted | 2026-08-19 |
| 015 | [Correct native squared L2 at the vector-store boundaries](015-correct-native-squared-l2-at-vector-store-boundaries.md)                   | Accepted | 2026-08-19 |

## Status values

- **Proposed** — under discussion, not yet agreed
- **Accepted** — agreed and active
- **Superseded** — replaced by a later TDR (link to superseding TDR)
- **Deprecated** — no longer relevant, not superseded by a specific TDR

Once a TDR is **Accepted**, never edit its decision — supersede it with a new
TDR and update the status here.
