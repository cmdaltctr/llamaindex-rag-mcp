# Design: fix-claim-splitter-non-claims

## Context

See proposal.md for the problem. This section records how the splitter works today. Each fact was checked by calling `split_claims(text, 3)` on the v3 branch at `d9dfc75`.

### How claims reach the judge today

- `_SENTENCE_SPLIT` (`src/omrg/core/answer/verify.py:38`) splits on `.`, `!` or `?` followed by whitespace, and on every newline. Each line is therefore its own segment. The splitter has no markdown awareness.
- `split_claims` (`verify.py:95-154`) loops over the segments (`:121`). It parses ordinals with `parse_citation_ordinals` (`verify.py:125`, `citations.py:38`), removes `[n]` markers (`verify.py:126`, pattern at `:42`) and tidies spaces (`:130`).
- A segment with no in-range ordinal is not a claim. It is kept as `last_text` (`verify.py:131-135`).
- A segment that is only a marker (for example `[1]` on its own line) attaches its ordinals to `last_text` (`verify.py:136-151`). This is the "Text. [1]" fix from CodeRabbit review. It attaches to any uncited segment, also a fence line or a heading.
- Every other cited segment becomes a claim (`verify.py:152`).
- `verify_claims` makes one judge call per claim (`verify.py:271-275`). `verified` is `not failing and not skipped_reason` (`verify.py:290`). With zero claims it returns `verified=True` and `calls=0` (pinned by `tests/test_answer_verify.py:606`).
- The stage runs only when the answer is grounded and `verify_claims` is on (`src/omrg/core/answer/stages.py:282`). "Grounded" comes from `parse_citation_ordinals` over the whole text, not from the claims.
- Any failing claim gives `status="unverified_claims"` (`src/omrg/core/answer/results.py:175-176`). The web shows "Unverified claims", amber (`web/src/chat/answerStatus.ts:38-43`).

So the splitter judges only cited segments. An uncited heading or fence line reaches the judge in two ways: the line itself carries a marker, or the next line is a marker-only line.

### Construct by construct

| Construct | Example input | Claims today | Reaches judge? |
| --- | --- | --- | --- |
| ATX heading, uncited | `## Installation` then a cited sentence | sentence only | No |
| ATX heading, cited on the line | `## Installation [1]` | `## Installation` (1) | Yes (`verify.py:152`) |
| ATX heading, then marker-only line | `## Installation` / `[1]` | `## Installation` (1) | Yes (`verify.py:136-151`) |
| ATX `######` cited | `###### Deep heading [2]` | `###### Deep heading` (2) | Yes |
| Empty ATX heading | `#` / `[1]` | `#` (1) | Yes |
| Not a heading (no space) | `#hashtag style line [1]` | judged as prose | Yes, correctly |
| Setext text line, cited | `Installation [1]` / `===` | `Installation` (1); `===` dropped | Text line yes, underline no |
| Setext underline, then marker | `Installation` / `---` / `[1]` | `---` (1) | Yes |
| Closing fence, then marker-only line (the live case) | `` ``` `` / `[1]` | `` ``` `` (1) | Yes |
| Closing fence with marker | `` ``` [1] `` | `` ``` `` (1) | Yes |
| Opening fence with marker | `` ```bash [1] `` | `` ```bash `` (1) | Yes |
| Indented fence (inside a list) | `  ``` ` / `[1]` | `` ``` `` (1) | Yes |
| Tilde fence | `~~~` | same as backtick fence | Same |
| Code line inside a fence, cited | `uv sync # see [1]` | `uv sync # see` (1) | Yes |
| Code line, then marker-only line | `uv sync` / `[1]` | `uv sync` (1) | Yes |
| Horizontal rule, then marker | `---` / `[2]` | `---` (2) | Yes |
| Horizontal rule with marker | `*** [2]`, `* * *` / `[1]` | `***` (2), `* * *` (1) | Yes |
| Bare list marker with marker | `- [1]` | `-` (1) | Yes |
| Bare numbered marker, then marker | `1.` / `[1]` | `1.` (1) | Yes |
| Table separator, then marker | `\|---\|---\|` / `[1]` | `\|---\|---\|` (1) | Yes |
| Table data row, cited | `\| x \| y [1] \|` | `\| x \| y \|` (1) | Yes, correctly (real content) |
| Any uncited line, no marker line after it | heading, fence, code, rule | none | No |
| Leading marker with nothing before | `[1]` / `Uncited text.` | none, so `verified=true`, 0 calls | No judge call |
| Inline code in prose | ``Use `## Title` syntax [1].`` | judged as prose | Yes, correctly |

Tests of `split_claims` today: `tests/test_answer_verify.py:336` (cited sentences only), `:558` (trailing citation attach), `:606` (zero claims). No test covers markdown structure.

## Goals / Non-Goals

**Goals:**

- Markdown structure lines never reach the judge.
- Prose claims next to structure are judged exactly as today.
- The fix stays inside `verify.py`, deterministic, with no new dependency.

**Non-Goals:**

- A full markdown parser. A small line classifier with a fence state flag is enough.
- Stripping leading list markers from real claims (`- Install uv [1]` stays `- Install uv`). The judge handles that text today.
- Bold pseudo-headings such as `**Installation**`. They are prose to a line classifier. Leave them for a later change if they show up.
- Any change to the judge prompt, the verdict parser, the reranker ÷30 calibration or experiment 20.

## Decisions

### D1. Classify each line before the sentence split

Walk the text line by line. Keep the open fence (its character and length), or none. The fence rules follow CommonMark:

- An opening fence is three or more backticks or tildes at the start of the line, after any indent (lists indent fences deeper than three spaces). A backtick fence's info string must not contain a backtick. So the line ```` ```uv sync``` installs it [1]. ```` is prose, not a fence.
- A closing fence uses the same character, at least as many of it as the opening fence, and nothing after it but spaces. So `~~~` inside a backtick block does not close it.
- The opening line, the closing line and every line between them are skipped.

Other structure lines are matched with small anchored patterns. The remaining lines go through the existing sentence split and attach logic unchanged.

A plain toggle on any fence-like line is not enough. The probe on `1d7d212` shows the inline case above is a real claim today. A toggle would open a fence there and hide every claim after it.

Alternative: use a markdown library (for example `markdown-it-py`). Rejected: a new core dependency needs approval, and the line rules are short and testable.

An unclosed fence skips to the end of the answer. That is the CommonMark rule too, and the model output for that case is code, not prose.

### D2. Setext headings: skip the underline only

`---` under a text line makes that line a setext heading in CommonMark. Models also write `Fact one [1].` then `---` as a section break. If the splitter dropped the line above every `---`, it would drop real claims. So the splitter skips the underline line and keeps the text line as a candidate claim. A short cited heading-like text line is then judged. That costs one call and can give a false amber badge, but it never hides a real claim.

### D3. A skipped line breaks the trailing-citation chain

When the splitter skips a line, it clears `last_text`. A marker-only line after a skipped line then cites nothing in the judge sense and is dropped. It does not attach to an earlier prose sentence, because that sentence did not cite it. The ordinal still counts for grounding and stays in `citations`, because those come from the whole text (`citations.py:38`), not from the claims.

### D4. Zero judgeable claims reports `verification_skipped`

After this fix, a grounded answer can have zero claims more often (for example, an answer whose only citation sits under a code block). Zero claims also happens today when the only marker leads the answer (`[1]` then uncited text). Today zero claims gives `verified=true` after zero calls. That claims a check that did not happen. The fix: when `verify_claims` finds no claim, it sets `skipped_reason="no verifiable claims (no cited prose sentence)"`. The reason names no construct, because the leading-marker case has no heading or code. `run_verification_stage` already maps a `skipped_reason` to `verification_skipped` with `verified` absent (`verify.py:373-380`), so the stage needs no change. The diagnostics report `verification_calls=0`. The status stays `ok`. The web already shows `verification_skipped` (`web/src/chat/AssistantTurn.tsx:81-83`) and shows the blue "Cited" badge because `verified` is absent (`answerStatus.ts:19-29`). The field is an existing free-text string (`openapi.yaml:5119-5124`), so only its description changes. This replaces the assertion in `tests/test_answer_verify.py:606`.

The main spec scenario "Verification enabled" says the result SHALL include a `verified` field whenever verification runs on a cited answer. That was already wrong: a failing run reports `unverified_claims` and a degraded run reports `verification_skipped`, and neither carries `verified` (`results.py:215-220`). D4 adds one more case without `verified`. So the delta spec modifies that requirement: the result reports exactly one outcome, `verified=true`, `unverified_claims` or `verification_skipped` (root gotcha 12: fix the baseline, do not work around it).

### D5. No new result field

The splitter leaves skipped lines out silently. `diagnostics.verification_calls` already shows how many claims were judged. A `skipped_lines` count would change the result shape, the OpenAPI schema, `web/src/api/documents.ts` and the graph adapter keys (`src/omrg/core/answer/graph_adapters.py:83`) for a number nobody acts on.

### D6. Unit tests only, no experiment rerun

Experiment 20 judges frozen claim–evidence triples from `ground-truth.json` and never calls the answer pipeline or `split_claims` (`experiments/20-citation-faithfulness-2026-09-02/run_eval.py:18-22`). Its gates (recall, false rejection, latency) measure the judge, which this change does not touch. The change removes inputs that were never claims, so the gates stay valid.

## Open questions for the user

The spec delta and tasks follow the recommendations below. If you choose another option, the delta spec and tasks change, so please answer before `apply`.

1. **What to skip.** Options: (a) headings and fence lines only; (b) also lines inside fences, horizontal rules, table separators and bare list markers. **Recommendation: (b).** The probe shows every one of these reaches the judge through the marker-only attach path, and none is a claim. A cited command inside a code block loses its check; the prose sentence that explains the command keeps its check.
2. **A citation on a skipped line** (for example `## Installation [2]`). Options: (a) drop the line from the claims, keep the ordinal for grounding; (b) keep the heading text as a claim. **Recommendation: (a).** A heading names a topic, so the judge has nothing to entail. Same rule for a marker-only line after a skipped line (D3).
3. **Report skipped lines?** Options: (a) silent; (b) add a count to the result. **Recommendation: (a), no contract change** (D5). Together with D4, the zero-claims case reports `verification_skipped`.
4. **Zero judgeable claims** (D4). Options: (a) report `verification_skipped` with a reason; (b) keep `verified: true` after zero calls. **Recommendation: (a).** It is the honest status and needs no shape change.
5. **Experiment rerun?** Options: (a) unit tests only; (b) rerun experiment 20. **Recommendation: (a)** (D6).

## Risks / Trade-offs

- [A model writes a real claim as a heading, for example `## Ollama needs 8 GB RAM [1]`] → The claim is not judged. Mitigation: the ordinal stays in `citations`; prose claims are the normal shape. Accept.
- [A cited command inside a code block is no longer checked] → Mitigation: the explaining sentence is still judged. Accept, per open question 1.
- [An unclosed fence hides the prose after it] → Mitigation: a test pins this; it matches CommonMark. If live answers show unclosed fences often, revisit.
- [A line classifier misreads an edge case, for example `---` inside a YAML block in a fence] → Mitigation: the fence state is checked first, so lines inside a fence are skipped before the rule check.
- [A fence-like prose line hides later claims] → Mitigation: the CommonMark open and close rules in D1. Guard tests pin inline triple backticks and a tilde line inside a backtick block.
- [`verification_skipped` for zero claims looks like a judge fault] → Mitigation: the reason text names the cause in plain words.

## Migration Plan

No data or settings migration. Roll back by reverting the commit. Answers made before the change are not re-verified.
