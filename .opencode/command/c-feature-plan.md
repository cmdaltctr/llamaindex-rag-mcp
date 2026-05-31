---
description: Quick OpenSpec feature planning with proposal, tasks, specs, and design docs. Usage: /feature-plan <feature-name> [description]
agent: a-plan
model: deepseek/deepseek-v4-pro
subtask: true
---

You are creating an OpenSpec feature plan. Write in British English.

1. **Parse**: feature name ($1, kebab-case for change-id), description ($2 + remaining args).

2. **Check OpenSpec**: does `openspec/` exist? If not, create minimal structure with `project.md` template. If yes, read `openspec/project.md` and `openspec/AGENTS.md`.

3. **Research if needed**: for non-trivial features, invoke:
   ```
   @a-tech-researcher Evaluate technologies for "$2"
   ```
   For auth/payments/data features, also invoke:
   ```
   @a-security Threat model for "$2"
   ```

4. **Create** `openspec/changes/<change-id>/`:
   - **proposal.md**: Summary, motivation, scope (in/out), success criteria, risks
   - **tasks.md**: Phased `- [ ]` checklist
   - **specs/<capability>/spec.md**: SHALL/MUST requirements with Given/When/Then scenarios
   - For complex: **design.md**, **risks.md**, **evaluation.md**

5. **Spec format**: `## ADDED / MODIFIED / REMOVED Requirements` with `### Requirement:` headers and `#### Scenario:` with Given/When/Then.

6. **Report**: ✅ Plan created at `openspec/changes/<change-id>/` → next steps for user.
