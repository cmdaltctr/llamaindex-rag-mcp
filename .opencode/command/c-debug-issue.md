---
description: Systematic debugging workflow — root cause analysis, fix, and regression test. Usage: /debug-issue <description>
agent: a-build
subtask: true
---

You are debugging an issue using the standard workflow.

## Pre-flight

1. **Load the build orchestrator prompt** — see the Bug Fixes section:
   Read `~/.config/opencode/prompts/a-build-orchestrator.txt`

2. **Load relevant skills** for the tech stack.

## Parse Input

- Issue description: $ARGUMENTS (full text)

## Workflow

### 1. Root Cause Analysis

@a-debug — "Root cause analysis: $ARGUMENTS"
Let a-debug investigate. It will:
- Reproduce the issue
- Form and test hypotheses
- Isolate root cause
- Report findings with file:line references

WAIT for a-debug to report before taking any action.

### 2. Implement Fix

Apply the fix proposed by a-debug (or adjust based on your judgement).
Do not change anything outside the scope of the bug.

### 3. Regression Test

@a-test — "Write regression test that reproduces the bug"
The test must:
- Fail without the fix
- Pass after the fix

### 4. Verify

Run all tests to confirm:
- Regression test fails without fix ✓
- Regression test passes with fix ✓
- All existing tests still pass ✓

## Report

```markdown
✅ Debug complete: [issue summary]

## Root Cause
[from a-debug report]

## Fix Applied
[files changed, diff summary]

## Regression Test
[test file location, test name]

## Verification
- [x] Regression test fails without fix
- [x] Regression test passes with fix
- [x] All existing tests pass
```
