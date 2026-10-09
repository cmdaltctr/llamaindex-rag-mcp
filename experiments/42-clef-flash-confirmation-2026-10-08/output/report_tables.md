| Arm | Junk caught | Recall (Wilson) | Healthy flagged | Rate (Wilson) | G1 | G2 | G3 |
| --- | ---: | --- | ---: | --- | --- | --- | --- |
| Production today (no check) | 0/76 | 0.0% (0.0% to 4.8%) | 0/358 | 0.0% (0.0% to 1.1%) | FAIL | PASS | PASS |
| Word check (A) | 49/76 | 64.5% (53.3% to 74.3%) | 1/358 | 0.3% (0.0% to 1.6%) | FAIL | PASS | PASS |
| Clef-flash Q8_0 W1 | 56/76 | 73.7% (62.8% to 82.3%) | 11/358 | 3.1% (1.7% to 5.4%) | FAIL | FAIL | FAIL |

| Arm | Document-cluster recall interval | Document-cluster rate interval | AUC | Rate at threshold x0.9 / x1.1 |
| --- | --- | --- | ---: | --- |
| Word check (A) | 48.6% to 85.7% | 0.0% to 0.9% | 0.854 | 0.0% / 40.2% |
| Clef-flash Q8_0 W1 | 57.1% to 85.3% | 0.9% to 5.8% | 0.969 | 2.0% / 4.2% |

| Arm | Rescued junk-layer documents missed (G1) | Rescued usable documents sent to OCR (G2) |
| --- | --- | --- |
| Word check (A) | `rs37` | none |
| Clef-flash Q8_0 W1 | `rs06`, `rs08`, `rs10`, `rs17`, `rs51`, `rs58` | `st08`, `rs11`, `rs23`, `rs32`, `rs34`, `rs59` |

Margin: recall difference +0.0921 (needs +0.10); McNemar Clef-only 25, A-only 18, one-sided p 0.1802 (needs < 0.05). Verdict: FAIL (OD1 A).
