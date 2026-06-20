---
description: Full security audit — dependency scan, code review, and threat modelling with remediation. Usage: /security-audit <change-id or path>
agent: a-build
subtask: true
---

You are running a comprehensive security audit.

## Pre-flight

1. **Load the build orchestrator prompt** — see the High-Risk Code section:
   Read `~/.config/opencode/prompts/a-build-orchestrator.txt`

2. **Load relevant skills** for the tech stack.

## Parse Input

- Target: $1 (OpenSpec change-id or file/directory path)
- If a change-id, read `openspec/changes/$1/` for context
- If a path, audit that file or directory

## Workflow

### 1. Security Scan

@a-security — "Vulnerability scan of [target]"
The scan covers:
- Secrets and hardcoded credentials
- Input validation at all boundaries
- Auth and authorisation checks
- Injection risks (SQL, XSS, command)
- Data exposure
- Dependency CVEs (bun audit / npm audit)

WAIT for the full security report before proceeding.

### 2. Remediation

For each finding from @a-security:
- Fix CRITICAL and HIGH severity issues immediately
- Report MEDIUM and LOW issues with recommended fixes
- Do NOT fix anything outside the scope of the security findings

### 3. Re-scan

@a-security — "Re-scan [target] after fixes"
Confirm all CRITICAL and HIGH findings are resolved.

### 4. Documentation

If findings were significant, update `openspec/changes/$1/risks.md`
(or create it) with the security assessment and remediation log.

## Report

```markdown
✅ Security audit complete: [target]

## Findings Summary
- CRITICAL: X (all fixed)
- HIGH: X (all fixed)
- MEDIUM: X (reported)
- LOW: X (reported)

## Remediation
[list of fixes applied]

## Rescan
- [x] All CRITICAL resolved
- [x] All HIGH resolved
- [ ] Outstanding MEDIUM/LOW items documented

## Risks Documented
[risks.md path or "N/A"]
```
