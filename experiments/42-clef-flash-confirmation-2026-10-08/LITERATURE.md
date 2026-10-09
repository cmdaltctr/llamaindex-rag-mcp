# Literature note: reference-free OCR text-quality estimation

- **Date**: 2026-10-09
- **Purpose**: compare the Experiment 42 method with published practice, after the verdict
- **Search**: Scopus first, then Semantic Scholar, arXiv, CrossRef and OpenAlex through `paper-search-mcp`. 17 papers were relevant. CrossRef verified 15 DOIs; 2 items are arXiv preprints without a DOI; 1 further item (reference 7) is unverified.
- **Depth**: for several papers, only the abstract and some passages from the PDF were read. Numbers marked "partial" may be incomplete.

## 1. Method families

| Family | What it measures | Examples |
| --- | --- | --- |
| Dictionary or lexicality rate | Share of tokens found in a word list, sometimes with historical spelling patterns | Alex and Burns 2014 [1]; Kettunen 2020 [10]; Springmann et al. 2016 [15]; van Strien et al. 2020 [17] |
| Character n-gram or language-model score | Likelihood or perplexity of the text under a character or word model | Booth et al. 2022 [2] (one model per decade); Ströbel et al. 2022 [16] |
| Garbage-string rules | Hand rules that flag one token as garbage | Kulp and Kontostathis 2007 [11]; Wudtke et al. 2011 [18] |
| Classifier on combined features | Dictionary, trigram, garbage-rule and metadata features in one model | Schneider and Maurer 2022 [14]; Cuper and den Boer 2025 [6]; Cuper [7] |
| Transformer regressor | Predicts word error rate from the OCR text only | Osório and Cardoso 2026 [12] |
| Engine confidence or image features | OCR engine confidence, layout geometry, or scan image before OCR | Springmann et al. 2016 [15]; Cuper et al. 2023 [5]; Gupta et al. 2015 [8]; Clausner et al. 2016 [4] |
| LLM-based score | Token entropy, or correction-based ranking of OCR engines | Kaltchenko 2026 [9]; Xu et al. 2026 [19] |

No peer-reviewed study of a yes/no LLM readability judge, the kind tested in Experiments 38 and 42, was found.

## 2. How the studies evaluate

- **Ground truth.** Almost always aligned human transcriptions, scored as character error rate (CER), word error rate (WER) or Levenshtein similarity. Alex and Burns [1] used human ratings on a 5-point scale for 100 documents.
- **Regression first.** Studies report how well the score tracks the error rate. Ströbel et al. [16] report Spearman ρ ≥ 0.94 for token ratio and character 7-gram ratio against CER on Latin lines, and 0.65 to 0.78 for statistical language-model perplexity. Gupta et al. [8] report r = −0.70 on 6,775 documents.
- **Classification second.** Schneider and Maurer [14] label a text block "insufficient" below a quality of 0.95 and report F1 and Cohen's kappa. Cuper [7] splits sentences at CER 10% and reports precision and recall.
- **Thresholds.** Usually fixed by hand, or chosen by ROC analysis on the same data [8]. Tests on a held-out collection, language or period are rare. Ströbel et al. [16] test on letters by different authors.
- **Decision unit.** Text block [14], sentence [7], line [16], box then document [8], document [1, 2].
- **Data and benchmarks.** About 7,000 blocks [14]; 94,000 sentences [7]; 825 lines [16]; 30,509 articles [17]. Post-OCR benchmarks: ICDAR 2017 and 2019 [13]; BLN600 [3].

## 3. Evidence on the Experiment 42 failure modes

- **Non-prose content.** No paper tests chart axes, formulas, verse or indexes directly. Indirect evidence: short blocks score low on dictionary rate and are "considerably harder to determine" [14]; non-alphanumeric tokens are dropped before scoring [2]; numerals count as good words [1]; only sentences of 7 or more words are scored [7]; non-text boxes are removed first [8].
- **Historical and multilingual text.** Recall rose from 0.05 to 0.46 when a modern Dutch dictionary was replaced by a historical one [7]. English garbage rules transfer poorly to 17th-century Dutch: F1 0.55 to 0.65, against 0.91 for a trained classifier [6]. One model per decade [2]; historical spelling patterns [15].
- **Common remedies.** Remove non-text first. Use a dictionary or model per language and per period. Set a minimum length.

## 4. Re-OCR routing and LLM judges

- **Closest to our problem.** Schneider and Maurer [14] predict the quality gain from a new OCR run with a regression model, and re-OCR a block only when the predicted gain exceeds a margin α (0 to 0.05).
- **Before OCR.** Clausner et al. [4] predict OCR quality from the scan image.
- **Document decisions.** No paper combines page scores into a document decision beyond a length-weighted error [14].
- **LLM work.** New and mostly not peer reviewed [9, 19]. None tests a judge on historical Latin or Spanish text.

## 5. A standard design for this question

1. **Target.** Page error rate (CER or WER) against aligned transcriptions. If a vision-LLM transcription is the reference, hand-check a sample and report its error rate.
2. **Metrics.** Spearman ρ and mean absolute error first; then precision, recall and F1 at the chosen threshold, with document-cluster bootstrap intervals.
3. **Non-text.** Remove it before scoring, by layout region or minimum token count. Report results by content type, language and period.
4. **Threshold.** Fit it on a development split grouped by document, weighted by the real cost of each error. Test on held-out collections (leave one collection or one language out).
5. **Decision unit.** Score pages, then decide per document by a length-weighted mean or a share of bad tokens. If possible, predict the gain from re-OCR.
6. **Baselines.** Token ratio, character 6-gram or 7-gram ratio and the garbage rules, beside any LLM judge.

## 6. Gaps in the literature

- No benchmark labels non-prose content in scanned PDFs.
- No study of hidden PDF text layers that someone else made earlier.
- Little testing across languages or periods with a frozen threshold.
- No peer-reviewed test of a yes/no LLM readability judge.
- No principled rule for turning page scores into a document decision.

## References

| # | Reference | DOI | CrossRef |
| --- | --- | --- | --- |
| 1 | Alex, B. and Burns, J. (2014). Estimating and rating the quality of optically character recognised text. DATeCH 2014, ACM. | 10.1145/2595188.2595214 | verified |
| 2 | Booth, C., Shoemaker, R. and Gaizauskas, R. (2022). A Language Modelling Approach to Quality Assessment of OCR'ed Historical Text. LREC 2022. | 10.63317/3kd8n7srb9vx | verified |
| 3 | Booth, C. W., Thomas, A. and Gaizauskas, R. (2024). BLN600: A Parallel Corpus of Machine/Human Transcribed Nineteenth Century Newspaper Texts. LREC-COLING 2024. | 10.63317/525gz987px5s | verified |
| 4 | Clausner, C., Pletschacher, S. and Antonacopoulos, A. (2016). Quality Prediction System for Large-Scale Digitisation Workflows. DAS 2016, IEEE. | 10.1109/das.2016.82 | verified |
| 5 | Cuper, M., van Dongen, C. and Koster, T. (2023). Unraveling Confidence: Examining Confidence Scores as Proxy for OCR Quality. ICDAR 2023, LNCS. | 10.1007/978-3-031-41734-4_7 | verified (full text not read; no findings used) |
| 6 | Cuper, M. and den Boer, E. (2025). Digging Through Garbage: Detection of 'Garbage' Words in Digitized Historical Documents. Anthology of Computers and the Humanities. | 10.63744/wd9byr0wxuta | verified |
| 7 | Cuper, M. (year not confirmed). Examining a Multi Layered Approach for Classification of OCR Quality without Ground Truth. DH Benelux Journal 4. | none found | unverified |
| 8 | Gupta, A., Gutierrez-Osuna, R., Christy, M. et al. (2015). Automatic Assessment of OCR Quality in Historical Documents. AAAI 29(1). | 10.1609/aaai.v29i1.9487 | verified |
| 9 | Kaltchenko, A. (2026). Page-Level Shannon Entropy From Top-k Logprobs Predicts OCR Quality. IEEE CCWC 2026. | 10.1109/ccwc67433.2026.11393782 | verified |
| 10 | Kettunen, K. (2020). How to Do Lexical Quality Estimation of a Large OCRed Historical Finnish Newspaper Collection with Scarce Resources. Digital Studies/Le champ numérique 10(1). | 10.16995/dscn.315 | verified |
| 11 | Kulp, S. and Kontostathis, A. (2007). On Retrieving Legal Files: Shortening Documents and Weeding Out Garbage. TREC 2007, NIST SP 500-274. | 10.6028/nist.sp.500-274.legal-ursinus-college.kontostathis | verified |
| 12 | Osório, T. F. and Cardoso, H. L. (2026). RoWeR: RoBERTa Word Error Rate Estimator for OCRed Texts. ICDAR 2026, LNCS. | 10.1007/978-3-032-36033-5_1 | verified (abstract only) |
| 13 | Rigaud, C., Doucet, A., Coustaty, M. and Moreux, J.-P. (2019). ICDAR 2019 Competition on Post-OCR Text Correction. ICDAR 2019. | 10.1109/icdar.2019.00255 | verified |
| 14 | Schneider, P. and Maurer, Y. (2022). Rerunning OCR: A Machine Learning Approach to Quality Assessment and Enhancement Prediction. Journal of Data Mining and Digital Humanities. | 10.46298/jdmdh.8561 | verified |
| 15 | Springmann, U., Fink, F. and Schulz, K. U. (2016). Automatic quality evaluation and (semi-)automatic improvement of OCR models for historical printings. arXiv:1606.05157. | none (preprint) | not applicable |
| 16 | Ströbel, P. B., Volk, M., Clematide, S. et al. (2022). Evaluation of HTR models without Ground Truth Material. LREC 2022. | 10.63317/5q7mf345k9h5 | verified |
| 17 | van Strien, D., Beelen, K., Ardanuy, M. et al. (2020). Assessing the Impact of OCR Quality on Downstream NLP Tasks. ICAART 2020. | 10.5220/0009169004840496 | verified |
| 18 | Wudtke, R., Ringlstetter, C. and Schulz, K. U. (2011). Recognizing garbage in OCR output on historical documents. J-MOCR-AND 2011, ACM. | 10.1145/2034617.2034626 | verified (metadata only) |
| 19 | Xu, Z., Wu, P., Lau, L. C. M. et al. (2026). DocOCR-Eval: A Correction-Based Framework for OCR Tool Selection Without Ground Truth. arXiv:2607.16203. | none (preprint) | not applicable |

## Open checks

1. Read the full text of reference 5 before using any finding from it.
2. Confirm the year of reference 7 in DH Benelux Journal issue 4.
3. FinePDFs (Hugging Face) publishes an XGBoost classifier that chooses between OCR and text-layer extraction, with an annotation set. There is no paper to cite; treat it as practice, not evidence.
