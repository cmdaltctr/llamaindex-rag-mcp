# dots.mocr licence notes

This file records the terms of the dots.mocr model licence that affect OMRG.
It is a record of terms. It is not legal advice.

- **Model:** `rednote-hilab/dots.mocr`, revision `e539fbb52280393adc081b289ec597430a0f9031`.
- **Licence:** "dots.mocr LICENSE AGREEMENT", effective 8 August 2025, copyright holder
  Xingyin Information Technology (Shanghai) Co., Ltd. The agreement is based on the MIT
  licence. The full text downloads with the model weights, as the file
  `dots.mocr LICENSE AGREEMENT` in the model folder.
- **Source of the quotes:** the copy downloaded for Experiment 34 at the pinned revision.
  The quotes below are verbatim. Only runs of narrow no-break spaces are shown as one space.

## Why provisioning asks for acceptance

`python3 ocr-workers/provision.py dots-mocr` stops before it installs anything unless the
operator adds `--accept-model-licence`. OMRG downloads the weights at provisioning time and
does not redistribute them. Commercial use and on-premises deployment are allowed (clauses
2.1 and 3.2).

With dots.mocr as the primary engine, every OCR route uses it: scanned PDFs, gate-selected
PDFs, escalated pages and maths pages. Clause 3.3(c) therefore applies to scanned books and
papers too. An operator who does not accept these terms leaves this engine unprovisioned.
PaddleOCR-VL (Apache-2.0) then serves the OCR routes as the fallback engine.

## Clause 1.6: order of precedence

> 1.6 Priority of Agreement. In the event of any conflict or inconsistency between this Agreement and the MIT License, the terms of the MIT License shall prevail. However, if the terms of the MIT License are ambiguous or silent on a particular matter, the provisions of this Agreement shall apply and supplement the MIT License.

## Clause 3.3(c): copyright restrictions

> 3.3 Prohibited Uses. Any breach of the prohibitions below will result in the automatic termination of all licenses granted under this Agreement. Licensee agrees not to use the Model Materials or any derivative works thereof, in connection with:
>
> (c) Copyright Restrictions:Licensees shall not use the tool for unauthorized digitization of publications/document scanning or bulk scraping of content. Any use involving publications or other copyright-protected materials must first obtain relevant permissions.

## Clause 5.2: privacy protection

> 5.2 Privacy Protection.
>
> (a) Sensitive‑Data Restrictions. It is prohibited to use the Model Materials to process,or extract infer sensitive personal data protected under specific laws (such as GDPR or HIPAA), particularly when dealing with documents containing personally identifiable information (such as ID numbers, health data, financial information, etc.), unless Licensee has obtained all necessary consents, lawful basis, or authorizations, and has implemented adequate anonymization, pseudonymization, or other privacy-enhancing technologies.
>
> (b) Data Minimization and Purpose Limitation. The Licensee shall follow the principle of data minimization when using the OCR Model, processing only the user data necessary for specific, explicit, and lawful purposes. Specifically, the OCR Model should avoid processing unnecessary sensitive data and ensure compliance with applicable privacy protection laws during data handling.
>
> (c) Transparency. Licensee shall provide clear and transparent privacy policies and terms of use when processing user data, particularly during document scanning and information extraction. .

## Clause 8: governing law and dispute resolution

> 8. Governing Law and Dispute Resolution
>
> 8.1 Governing Law. This Agreement shall be governed by and construed in accordance with the laws of the People’s Republic of China, without regard to its conflict of laws principles.
>
> 8.2 Dispute Resolution. Any dispute claim, or disagreement arising out of or relating to this Agreement shall first be resolved through amicable consultation. If such consultation fails, the dispute shall be submitted to the Hangzhou Arbitration Commission for arbitration. The arbitration shall be conducted in accordance with the laws of China, and the place of arbitration shall be [Hangzhou, China]. The arbitral award shall be final and binding upon both parties.

## Clause 9: revised terms

> 9. Regulatory Compliance Amendments
>
> In the event that any part of this Agreement becomes invalid or requires adjustment due to changes in applicable laws or regulations, Licensor reserves the right to issue a revised version of this Agreement. Licensee shall migrate to the new version within [e.g., ninety (90)] days of its release; otherwise, all rights granted under this Agreement shall automatically terminate.
