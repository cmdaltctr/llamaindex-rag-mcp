# Security assessment: make-lancedb-default-and-isolate-chromadb

- **Date:** 2026-08-21
- **Scope:** Packaging and objective security evidence for tasks 1.3–1.6
- **Auditor:** a-security
- **Verdict:** **BLOCKED**

## Finding

### [GATE BLOCKER] Residual Chroma advisory lacks policy-owner disposition

The base wheel and fresh installation exclude Chroma. The universal all-extras lock still includes `chromadb==1.5.9`, which `pip-audit 2.10.1` reports under `PYSEC-2026-311`, `GHSA-f4j7-r4q5-qw2c`, and `CVE-2026-45829`, with no fix version listed.

Design D9 requires a real named owner's dated decision and signature. Owner remains `TBD`. No risk acceptance exists.

## Dependency audit

- Base artefact scan: 133 dependencies, zero known vulnerabilities.
- Fresh base install scan: 133 dependencies, zero known vulnerabilities.
- Universal all-extras scan: 179 dependencies, one known vulnerability in Chroma.

## Verdict justification

Release remains **BLOCKED** until the disposition template in [`04-residual-lock-finding.md`](04-residual-lock-finding.md) is completed. See [`00-verdict.md`](00-verdict.md) for all evidence and checklist results.
