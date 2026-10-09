# Experiment 42 report: Clef-flash confirmation

**Verdict: FAIL.** Under OD1 option A, a PASS needs G1, G2 and the margin; Clef-flash Q8_0 W1 failed all three. G3, which is secondary, also failed: Clef-flash flagged 11 of 358 rescued healthy pages, a rate of 3.1% (Wilson 95% interval 1.7% to 5.4%) against a 2% ceiling. Following design D10, work on text-only rescue signals stops.

- **Date**: 2026-10-09
- **Protocol**: [`protocol.md`](protocol.md), plan [`plan.json`](plan.json) (amendments A1 to A9)
- **OpenSpec change**: `experiment-42-clef-flash-confirmation`
- **Source of every number**: `output/summary.json` (tables printed by `analysis.py` into `output/report_tables.md`)

## What was tested

This was not an OCR test. pdf-inspector reads every PDF. When it fails silently (it says a page has text, then extracts nothing), the chain rescues the document with LiteParse (ADR-066). Production then trusts the rescued text and indexes it, even when the hidden OCR layer it came from is garbage (TDR-024).

The question was this: when production rescues a document, can Clef-flash read the rescued text and send junk documents to OCR without also sending good documents? Both thresholds were frozen on Experiment 38 data before any download. The reference transcription (Gemini 3.8 Flash, the engine behind the Experiment 33 and 38 labels) was a measuring tool only.

## Population

- **Documents.** 68 rescued documents with no Experiment 33 overlap. 8 came from the first 130 documents, and 60 from screening ACL Anthology 1989 to 1991, Archive.org Sevilla collections and NASA NTRS scans (amendment A8). Production rescued all 68 with LiteParse and routed none of them to OCR.
- **Document labels.** 36 `usable`, 19 `needs_ocr`, 13 `ambiguous`. 19 documents have a junk text layer.
- **LiteParse page classes.** 76 junk, 358 healthy, 7 grey and 171 excluded. Most exclusions are `ambiguous` Sevilla handwriting pages.
- **Targets.** Every A8 target passed (`output/set_check.json`). The largest one-document share of junk pages was 11.8%.
- **Reference cost.** USD 3.38 on OpenRouter against the USD 9.00 cap. 1 page of 612 had a parse error and is excluded.

## Results (LiteParse text, rescued documents)

| Arm | Junk caught | Recall (Wilson) | Healthy flagged | Rate (Wilson) | G1 | G2 | G3 |
| --- | ---: | --- | ---: | --- | --- | --- | --- |
| Production today (no check) | 0/76 | 0.0% (0.0% to 4.8%) | 0/358 | 0.0% (0.0% to 1.1%) | FAIL | PASS | PASS |
| Word check (A) | 49/76 | 64.5% (53.3% to 74.3%) | 1/358 | 0.3% (0.0% to 1.6%) | FAIL | PASS | PASS |
| Clef-flash Q8_0 W1 | 56/76 | 73.7% (62.8% to 82.3%) | 11/358 | 3.1% (1.7% to 5.4%) | FAIL | FAIL | FAIL |

| Arm | Document-cluster recall interval | Document-cluster rate interval | AUC | Rate at threshold ×0.9 / ×1.1 |
| --- | --- | --- | ---: | --- |
| Word check (A) | 48.6% to 85.7% | 0.0% to 0.9% | 0.854 | 0.0% / 40.2% |
| Clef-flash Q8_0 W1 | 57.1% to 85.3% | 0.9% to 5.8% | 0.969 | 2.0% / 4.2% |

| Arm | Rescued junk-layer documents missed (G1) | Rescued usable documents sent to OCR (G2) |
| --- | --- | --- |
| Word check (A) | `rs37` | none |
| Clef-flash Q8_0 W1 | `rs06`, `rs08`, `rs10`, `rs17`, `rs51`, `rs58` | `st08`, `rs11`, `rs23`, `rs32`, `rs34`, `rs59` |

**Margin.** Clef-flash recall exceeded the word check by 0.092, short of the required 0.10. McNemar counted 25 junk pages caught by Clef-flash only and 18 caught by the word check only, giving a one-sided p of 0.180 (the margin needs p < 0.05). H2 fails.

**Speed.** Clef-flash took 0.69 s per page at the median (mean 0.73 s, 95th percentile 1.20 s, n = 873), one request at a time. The build was llama.cpp b11510 with `-b/-ub 8192` (A5). 0 of 875 requests failed.

## Why Clef-flash failed

1. **Healthy pages are flagged above the frozen rate.** At the threshold fitted at 2% on Experiment 38, Clef-flash flagged 3.1% of new healthy pages. Experiment 38 measured 2.3%. The rate is steep near the threshold: it is 2.0% at ×0.9 and 4.2% at ×1.1.
2. **Short rescued documents turn one false flag into a whole-document route.** All six usable documents sent to OCR were sent on 1 to 4 flagged pages each. Five have 10 pages or fewer, so one flag already reaches the 10% routing share. The six would cost 58 pages of OCR, about 37 minutes at the dots.mocr rate of 38.2 s per page.
3. **Junk spread thinly across documents is missed.** The six missed junk-layer documents are Sevilla handwritten archives with 1 to 3 junk pages each. Most of their other pages are `ambiguous` and are not scored. Clef-flash caught 1 of their 9 junk pages; the word check flagged enough of them to route all six.
4. **Ranking is better than any single cut.** Clef-flash ranks junk below healthy far better than the word check (AUC 0.969 against 0.854). The frozen single threshold cannot turn that ranking into a routing decision that passes both G1 and G2 on short documents.

## The word check (A)

The word check came within one document of passing the primary gates. It missed `rs37`, an ACL paper with 1 junk page among 6, and sent no usable document to OCR. It flagged 1 of 358 healthy pages. Under design D10 it still counts as a FAIL (row 3), because G1 failed. This is an observation for the operator, not a change of verdict. Its threshold sits on a cliff: at ×1.1 its healthy flag rate jumps to 40.2%.

## Limits

- **Operator label check waived (A1).** No person reviewed the labels against page images. The 60-page stratified sample is listed in `output/label_check.json`, and the renders are in `output/.pages/`.
- **Routing counts flags only on scored pages.** As in Experiment 38, grey and excluded pages carry no score, so they cannot help a document reach the 10% share. Production would score every rescued page. This lowers G1 for both signals, mostly on the Sevilla handwriting documents. It does not explain G2 or G3, which fail on clean pages.
- **Sources differ from Experiment 38.** The rescued set is 30 ACL papers, 24 Sevilla archive items, 2 other Archive.org scans and 12 NASA scans, chosen by the shipped reader's own routing output. Experiment 38 used the Experiment 33 strata. The threshold may transfer differently to other rescued collections.
- **Reference engine change (A7) and poppler (A9).** The labels come from the Experiment 33 procedure, imported unchanged and run on this machine's poppler 26.10.0. Experiment 33 used an earlier poppler build.
- **Population change (A8).** The gates were restated for rescued documents before any label existed. The fast-path and OCR-routed documents (122 of the first 130) are outside this test.

## Conclusion and next action

H1 and H2 fail; H3 (secondary) fails. Clef-flash Q8_0 W1 at the frozen threshold is not adopted as the rescue-quality gate.

Following the D10 outcome table, the run records the failed gates and documents above and stops work on text-only rescue-quality signals. Task 7.1 opens no follow-up change.

The operator may still decide whether the word check's near-pass (G1 missed on one document) or Clef-flash's ranking (AUC 0.969) justifies a new, separately pre-registered proposal. Examples would be a document-level rule that does not route on a single flagged page, or a check that scores every rescued page. Any such proposal is a new experiment on new documents, and its thresholds cannot be fitted on this set.
