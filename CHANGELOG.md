# CHANGELOG

<!-- version list -->

## v3.0.0 (2026-08-28)

### Bug Fixes

- Address code review findings and base-install CI failure
  ([`1390aa2`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1390aa2c55e57fc379953028f18c91c14b1a28ca))

- Address CodeRabbit re-review on the LanceDB backend
  ([`97f00ff`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/97f00ffaa4db5bc4142eee6bbb646b6af3127cdc))

- Address CodeRabbit review findings
  ([`21843f1`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/21843f1ad92f47a70602f80006382278a464c666))

- Address CodeRabbit review findings
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- Address CodeRabbit review findings on PR #54
  ([`dad336c`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/dad336c9eb618d63ca7b3bf75502547d7752a29f))

- Address CodeRabbit review on PR #42
  ([#42](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/42),
  [`4cc267f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4cc267f1156dd7315ed489f6af5b242d5a0f63db))

- Address CodeRabbit review on PR #47
  ([`4ae5a59`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4ae5a59cdd07e38b64ed53130c31855057baa6f5))

- Address deferred reranker tech-debt (issues #38, #40, #41)
  ([#42](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/42),
  [`4cc267f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4cc267f1156dd7315ed489f6af5b242d5a0f63db))

- Address review findings on the LanceDB backend
  ([`6769667`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/67696679d924f6785a7ceaf98a03f0ab6682ab38))

- Address second LanceDB review round (filters, upserts, pagination)
  ([`24f5886`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/24f5886d0d3e44d3e229e81a79e7ea1932b25a9a))

- Align _SimpleBM25Okapi IDF with rank_bm25 and fix tiny-corpus tests
  ([`47350fb`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/47350fb034430aa9216ac683044d8390c4174491))

- Allow chroma_cloud as a chromadb import site in lint contract
  ([`308a509`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/308a509a20ea5f24c0d40cd5b70460ae7accad79))

- Apply CodeRabbit auto-fixes
  ([`70e0094`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/70e0094943116b4fb0bc084586d843cd29fb8e21))

- Apply CodeRabbit review findings
  ([`95f0f46`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/95f0f46ee8056213e526eeb9db2c7aba9bf1bae9))

- Apply the sparse-backend fallback to the field it validates
  ([`8423131`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/84231318857439beccd5242a77efac554bce0226))

- Close LanceDB default runtime spec gaps
  ([`debca40`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/debca4090684312cce1ed07f3d506a013cdd5c90))

- Correct classify rename follow-ups from PR review
  ([`ea23e06`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ea23e0619ea7f3b7c0860b80736638402938838a))

- Correct IDF clipping comment — 'more than half', not '≥ half'
  ([`6f0842c`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/6f0842cf3f0701ba9a19979e859c4d1e15b7f658))

- Distinguish flat vs nested retired env vars and harden provider tests
  ([`07a1b09`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/07a1b091305b6b6e60a99af3257628964f6fd3a6))

- Extend the retirement guard and correct stale provider values
  ([`aaa95ac`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/aaa95acacf2763dbc870898ee3c3fb6fdd110407))

- Extract _read_max_position_embeddings as shared module-level function
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- Harden PR #42 reranker tripwire test and model-config helpers
  ([#43](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/43),
  [`b09d7d0`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/b09d7d080035302a2f753c8a616c7c845c47c4c9))

- Keep lance adapter at the line ceiling; allow chroma_cloud import site
  ([`a57f599`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a57f59941d3930f7ef0eb126d901f1d9c9154ffd))

- Pass the LLM timeout under the keyword OpenAILike accepts
  ([`545c797`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/545c797da706e87775845a9e4a856078b0fdb330))

- Reject bool and negative pad_token_id in model config helper
  ([#43](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/43),
  [`b09d7d0`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/b09d7d080035302a2f753c8a616c7c845c47c4c9))

- Remove the residual dead-mechanism references and tighten the guards
  ([`a0d35ae`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0d35ae23bd4ccf0aa1dbe30d64b463518595f9e))

- **.gitignore**: Add .ua to ignore generated artifacts
  ([`c9ac838`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c9ac838fc476e40935995cd565ecb88c47d7fe88))

- **chunking**: Deterministic code splitting and metadata budget (Stage 1)
  ([`6c4b7c9`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/6c4b7c9a00c607c13b170de3542ab3cbe7751297))

- **ci**: Copy packages from uv cache
  ([`9c641fe`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/9c641fec864be300e710847054254464aa92a24b))

- **ci**: Force uv copy install mode in floors job
  ([`7a1523c`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7a1523c27b2c1241928d79a7c8db8b7635ee8def))

- **ci**: Keep Codecov report authoritative
  ([`077b835`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/077b8357bea90aac23e762ac743f59741da18c06))

- **ci**: Restore reset_model_cache re-export and fix setup-python SHA
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- **ci**: Upload torch coverage to merge with fast suite
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- **compose**: Defer runtime setup until startup
  ([`3e61ff8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/3e61ff8d61364269c57121744a613ed2f938ddc6))

- **compose**: Propagate construction failures from ensure_runtime_setup
  ([`e678e70`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e678e7057386785de8b6090fc91e272962cc79a9))

- **config**: Accept pdf-inspector reader selection
  ([`9cf1cf8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/9cf1cf883e6d9bff8cc5ee4937fb62d31a05b838))

- **config**: Raise on unrecognised provider-selection values
  ([`7b7d4fe`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7b7d4fef77d78b2ef5103f81616e7fc7f2b9def5))

- **config**: Validate concrete LLM backend, not the local/cloud alias
  ([`62a063d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/62a063d3023501a75dfc9f394076cfaf31bf356b))

- **config**: Validate strategy names at startup
  ([`dd3d490`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/dd3d490be52d3c8cce1486b31d0d6c4b8018c117))

- **core**: Keep base install green and cover partition-contract branches
  ([`351b996`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/351b9966e5008cec3b25b65a51a614f3c64230e4))

- **coverage**: Add fast tests for torch backend fallback path
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- **coverage**: Cover _read_max_position_embeddings and backend edge cases
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- **daemon**: Close TOCTOU window in _sha256_file size enforcement
  ([`5965335`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/596533540e83ba58c1fdd5c89006c5c96cfa9dd4))

- **experiments**: Amend 5b protocol to v1.1 with honest longevity budget filter
  ([`89977fa`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/89977fa6011af05af7a0234d2a6ff11141c2f548))

- **experiments**: Bootstrap EffectiveSettings in exp14 build+eval entry points
  ([`86e4149`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/86e414959a34080b7c7431efe14be11d3422acd1))

- **experiments**: Complete exp14 parser evidence
  ([`4a03627`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4a03627ad22ca5d269e03b9b8b26a8271a0c5e73))

- **experiments**: Correct G2 collection name and G7 v1-only marker in 19
  ([`a57abf3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a57abf372db521f201788662591da14c4dceabe0))

- **experiments**: Correct unreranked spelling in 5b protocol and plan
  ([`b013ae6`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/b013ae60c809c068130af09b99a72bf82219e87e))

- **experiments**: Create run directory before manifest freeze in 19
  ([`597dd54`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/597dd54ebd4defffba22801abdda5309740108f1))

- **experiments**: Exp14 eval reads frozen qrels; report pdf_inspector arm
  ([`5496a36`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/5496a36de55fe5630363c97b1a887449670ed077))

- **experiments**: Freeze corpus manifest file for 19 campaign identity
  ([`59d2fe5`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/59d2fe5e634581a52eb1d38ef1070d9cf75b7da9))

- **experiments**: Harden 5b harness against audit findings
  ([`636c31d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/636c31dff7222941da97eb882cd664ec140da031))

- **experiments**: Install default EffectiveSettings in 10b harness runtime
  ([`873e6d3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/873e6d361dfa764324cd6408a2d2a1af1a2ade82))

- **experiments**: Repair two 5b harness defects found by the campaign
  ([`5a6c530`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/5a6c530eaab37ea077042546dd98e42c1d8ff441))

- **experiments**: Resolve failing executable portably in 5b audit regression test
  ([`359f5fb`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/359f5fb72c1b79353d1dea1db5d09ac3fb739984))

- **experiments**: Retain diagnostic IDs in exp14 evaluation
  ([`c41498c`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c41498ccac5e8058bb9b27d651e9bb7652a511ef))

- **experiments**: Use nested env name for sparse backend in 19 campaign
  ([`f1d7e15`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/f1d7e15efb1dd19ae016559abdf71a42a9eca8ae))

- **ingestion**: Bind source identity to runtime embedder
  ([`7a18268`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7a18268348bd6edf5abe3319c26b6b5d9e1d8e72))

- **ingestion**: Close review gaps in identity, single-file routing, and PDF CI
  ([`4fa9a40`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4fa9a40c057123d3c70ec9d2ebccecf2e734c314))

- **ingestion**: Count degradation on observation, not replacement success
  ([`8defc05`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/8defc05003c85cab9d7478f47516a0dbfad633fd))

- **ingestion**: Delete legacy stale rows by ID
  ([`4fd0938`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4fd093817a7f1814615b36543ef2b0cf51a7cbaf))

- **installer**: Consent-gated replacement of differently-labelled watchers
  ([`3ed0f65`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/3ed0f6510e2498057e1b3c48aa9438521b201760))

- **installer**: Defer old-watcher removal past abort gates; probe failed bootouts
  ([`3599755`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/3599755d2e782138f4d920ae5f63de882256a40d))

- **installer**: Scope ingest-gate abort message to LaunchAgent writes
  ([`51d3724`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/51d372423bdec71c8564a8a6571539ebd46aca58))

- **lancedb**: Widen null-typed adapter columns before write
  ([`25ae9c3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/25ae9c30617dd26cd7cf207f92045e6bcc842bcd))

- **metadata**: Address review findings 1,2,4,5,6
  ([`7b360a4`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7b360a4d9c959c1889c7ce4895a8baf7a2742fd2))

- **metadata**: Include metadata_degraded on all ingestion result dicts
  ([`b578735`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/b5787357851a5d01079ac131555021c521949ba0))

- **metadata**: Signal degradation when llamaindex pipeline yields no usable metadata (finding 3)
  ([`295927c`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/295927c2023bd947ce5fcaff487b80e5766a72dc))

- **pdf**: Address review follow-ups for reader promotion
  ([`c567aef`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c567aef5ae212a91c30288fe06bb556a2ee273bf))

- **providers**: Correct relative config import depth
  ([`f2b71a7`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/f2b71a703620d85edb80673c7f17aebc66724628))

- **reranker**: Address CodeRabbit/Greptile review findings on PR #27
  ([`c638a0d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c638a0da257fe80ea3cfe394189d6a3f4a3d3847))

- **reranker**: Escalate persistent failures and fix threshold-outcome mismatch
  ([`3e3b8b7`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/3e3b8b7e0c5816fd9412e5c89a23a15fabaf3968))

- **reranker**: Reset last_failure_reason at the start of each rerank() call
  ([`e04f5c8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e04f5c8f228bfaeafaa82011d8a3c08017badf88))

- **retrieval**: Enforce semantic swappability contracts (Stage 2)
  ([`6dffece`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/6dffece298bec1507642cff15bbf03225f22af78))

- **spec**: Define drift-exemption policy in dependency-floor-integrity spec
  ([`1c73b07`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1c73b072e83f8b0f7694fa07c7887a829c6de394))

- **tests**: Normalise Rich help output
  ([`ae6bd6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ae6bd6b5ff6dd03bd5b786c1c4304d0f96bd9c29))

- **vectordb**: Apply sqrt to native L2 before canonical score transform
  ([`7bf16b3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7bf16b3eb2d994e7a3bdecaf75861a92013b5749))

- **vectordb**: Detect broken required backend imports
  ([`39e9e3b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/39e9e3b9fd708ffba1cbe3653be40bbd3c05b0dd))

### Chores

- **deps**: Raise dependency floors to tested versions
  ([`e1b6655`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e1b66551b353a68e7b942ea2980319b70823a366))

- **deps**: Upgrade huggingface-hub to 1.0 + transformers to 5.0
  ([`2aa2e2e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2aa2e2e175dca248084d220fd24c90d67026ce34))

- **deps**: Upgrade mcp to 2.0.0 (FastMCP -> MCPServer)
  ([`95fa556`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/95fa556a2b11228f4713f0d6e40273df0d5d9358))

### Features

- Add hosted Chroma Cloud backend for experiment storage
  ([`dc3f35e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/dc3f35e6a1b95e2e758b7756ef20aacb0e5d3f6a))

- Add install-login-watcher macOS LaunchAgent installer
  ([`8397be8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/8397be8e9ebe65364907db1dfce4a10bcddae4fb))

- Add lancedb vector-store backend with registry dispatch
  ([`5fd93c2`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/5fd93c2ca42d9e9e085082d36285013020779750))

- Dispatch document backends through a registry with orchestrated fallback
  ([`5e36c66`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/5e36c66d791bfc4fdc4b731ccf59ab2a499a9f62))

- Move chroma into optional extra and isolate the base test suite
  ([`e5af622`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e5af622bacd0e41098d16de5efc06bdd74c748e6))

- Redact all cloud credentials and accept provider-prefixed embedding IDs
  ([`9b14ead`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/9b14eadeaf9ad2a7037f3caca07c9748c1ecac6d))

- Route every LLM backend through the registry, name the pipeline timeout
  ([`2bd21bf`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2bd21bf183ae9e47e2e17c3b367460975b633853))

- Shape-aware retirement lifetime policy and guard test
  ([`01e409e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/01e409eeb143f537cc1db2932644077a1a108605))

- Wire OpenRouter into the LLM provider registry
  ([`bd0899e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/bd0899e62f3ea39af74176368813832ca593d25d))

- **chroma**: Support stale row ID deletion
  ([`7da3d39`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7da3d3973c608a2b24c0cf9c8934f1e9e962b2f5))

- **core**: Add optional Leiden community detection
  ([`ae9820a`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ae9820a6ebbe29e6d3a53f651b52d1fb822864d9))

- **core**: Add shared community strategy registry with seeded Louvain
  ([`5d9d0b8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/5d9d0b894e6ea0c6615d982b5726fc4286e79bfb))

- **experiments**: Add 19 LanceDB lifecycle qualification campaign
  ([`bed4fe9`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/bed4fe97537366eb9c5e63f2594f9bbc981a26bf))

- **experiments**: Add 5b campaign runner and lifecycle probe battery
  ([`09e823b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/09e823b835283761639a613c7cdc15c68d481fc2))

- **experiments**: Add 5b pre-run plan validator with ONNX/Torch parity rejection
  ([`c08cb4e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c08cb4ec109c3f92c1f1a02268c53a12fe0cc5a4))

- **experiments**: Add 5b protocol frames, worker prototype and artefact schemas
  ([`01b880d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/01b880d0613947c2fb254f67984e15d56b10b453))

- **experiments**: Add 5b supervisor, harness, materialiser and summariser
  ([`31f37df`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/31f37df88ee662f583316b30b8cd46e56323f8de))

- **experiments**: Add shared runtime manifest, preflight, and stats helpers (Stage 4.1/4.2/4.4)
  ([`53ba31b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/53ba31bf3f381163605440b6b9bba43884ec17dd))

- **experiments**: Apply ADR-049 vector-store policy to pending Stage 6 harnesses
  ([`2d575e7`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2d575e72c809291e3ad7c071ea4b1b5679b70334))

- **experiments**: Extend exp14 to three-parser A/B/C (protocol v2.1)
  ([`dd1623a`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/dd1623a1cea52dacfce95dc0a9d8c6a5e97eddc0))

- **experiments**: Merge per-unit artefacts in 5b summariser and tick sections 2-5
  ([`874cab4`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/874cab4376d7e9aba0dc76ba449b25d3c70a4a86))

- **experiments**: Re-base D17 harness immutable inputs on LanceDB
  ([`a4d3891`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a4d3891354fcd876f2edadb20c21186098835c62))

- **experiments**: Record 19 campaign run2 verdict 14/14 PASS
  ([`527842e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/527842e7fa006e27a86b8ef7e0ba5bd095981444))

- **experiments**: Record 5b per-block power and thermal context
  ([`eb56ed1`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/eb56ed10c0b540c08b7c877988786f994246bed3))

- **ingestion**: Add failure-safe source replacement
  ([`80e4d99`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/80e4d99dde1d4d076027c6788c1069696e7eb8cd))

- **ingestion**: Add peak RSS diagnostics
  ([`9325216`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/9325216fa945e25d8a8390c6e158261a965649cd))

- **ingestion**: Define complete source identity
  ([`c59b95a`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c59b95afbebe7694bdc6b84c6f8ce61281c6e7a5))

- **ingestion**: Narrow write lock to the mutation section (Stage 3B)
  ([`b4b01b6`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/b4b01b6780d5a13b5e8dca15970313bc3b9c98c6))

- **ingestion**: Process bounded failure-safe sources
  ([`746057f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/746057f916dddd09299b4c4095aa405fc5627327))

- **lancedb**: Support stale row ID deletion
  ([`c3e4c0a`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/c3e4c0a2b0cbec2151a92c3f7083fc4cc60eb808))

- **metadata**: Per-provider timeouts and degradation surfacing
  ([`520ffd5`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/520ffd576e5983fe63351371c4747472b6fa923f))

- **pdf**: Add pdf-inspector reader adapter (opt-in extra)
  ([`003dc15`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/003dc152251f46328bf901ef82abfbeb92278c53))

- **pdf**: Configure pdf_inspector as default reader
  ([`843f90f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/843f90f161dd10ef7f7692bbc014c50ae3536bbd))

- **reranker**: Pluggable reranker backend with torch-free default
  ([#37](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/37),
  [`7d58a33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7d58a33b1c3a0e273d2353bd5dbee64496b9026d))

- **vectordb**: Add store-neutral row ID deletion
  ([`abbabbe`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/abbabbe6cdcfaa9efcb931fe0965dc529b615243))

- **vectordb**: Enforce fail-closed embedding write contract
  ([`ebc934b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ebc934b964fa53f0acc0bad83b318d0b6be2fc5f))

- **vectordb**: Registry availability metadata, fail-closed legacy Chroma, backend summaries
  ([`2deeaee`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2deeaee8af93b7c2396e9b85fa2aed70bb46e8e7))

### Refactoring

- Rename ollama_classify_* settings to neutral classify_* names
  ([`7f26ee4`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7f26ee455a007e8fb816f0f763b730606ce415ee))

### Breaking Changes

- Rename to classify_max_attempts and classify_timeout.

- **deps**: Chromadb>=1.0.0, tree-sitter-language-pack>=1.12.3, tree-sitter>=0.23.0,
  llama-index>=0.14.5, llama-index-llms-ollama>=0.9.0, llama-index-vector-stores-chroma>=0.5.0,
  llama-index-readers-file>=0.5.0, llama-index-embeddings-ollama>=0.7.0,
  llama-index-embeddings-openai>=0.5.0, llama-index-llms-openai-like>=0.5.0, watchdog>=5.0.0,
  networkx>=3.2, onnxruntime>=1.20.0, ruff>=0.16.0


## v2.2.0 (2026-08-07)

### Bug Fixes

- **spec**: Make the downgrade budget interaction explicit
  ([#20](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/20),
  [`ae2cbf3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ae2cbf34f0c6c8b4bc29bdd43f51cdb07134d8c3))

### Features

- **metadata**: Enforce structured JSON output in LLM classification
  ([#20](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/20),
  [`ae2cbf3`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/ae2cbf34f0c6c8b4bc29bdd43f51cdb07134d8c3))


## v2.1.0 (2026-08-06)

### Features

- Add settings for graphify hooks and enhance AGENTS.md with graph usage guidelines
  ([`dbd6fde`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/dbd6fde96feebb33d6f252b4ffcc04a7352f77b2))


## v2.0.0 (2026-08-05)

### Bug Fixes

- Address all a-review blocking findings
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Address Phase 4 review findings (HIGH + MEDIUM)
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Address Phase 4 review findings (HIGH + MEDIUM)
  ([#15](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/15),
  [`239a634`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/239a6345da5c742d911346c585d8a634d980d3a0))

- Resolve all SonarQube code quality issues and security hotspots
  ([#11](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/11),
  [`44d116b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/44d116b7afbb7ce104546e7d00cdecf6602c4ce2))

- **ci**: Remove --no-build flag incompatible with editable installs
  ([#11](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/11),
  [`44d116b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/44d116b7afbb7ce104546e7d00cdecf6602c4ce2))

- **ci**: Set OLLAMA_BASE_URL env var for test collection
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

- **ci**: Strip ANSI codes in CLI help tests, remove pdf-liteparse matrix
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **doc-graph**: Use explicit len check for empty embeddings list
  ([`75b0925`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/75b092548513e3a571aab342d6baf4a727b8e336))

- **reranker**: Disable CoreML provider, fix silent inference failure
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

- **sonar**: Make _detect_native_sparse_capability runtime-dynamic
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

### Features

- Add profiles system for dual use cases (Phase 4)
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Add profiles system for dual use cases (Phase 4)
  ([#15](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/15),
  [`239a634`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/239a6345da5c742d911346c585d8a634d980d3a0))

- Codebase map, Azure reader, type-aware ingestion, SonarCloud security gate
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- Provider registry pattern with OpenRouter cloud provider
  ([`8703165`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/870316500ae0f8bbf5df18383f4f61d806d34498))

- **azure**: Add Azure Document Intelligence reader and type-aware ingestion
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **codebase-map**: Add fast-context codebase map with boundary validation and graph fixes
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **experiments**: Add Jupytext analysis workflow for experiment evaluation
  ([`816da98`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/816da98a8884abb300bcc50f62d439f9cb399e52))

- **reranker**: Swap default model to Alibaba-NLP/gte-reranker-modernbert-base
  ([`8f4fed2`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/8f4fed2ddd07ab2d126cec3c53a57b03296db323))

- **retrieval**: Add fetch_k override for experiment pool sweeps
  ([`49b7bc8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/49b7bc8ab91492cce51bd443e30927b461236897))

### Refactoring

- Architecture-v2 conformance (v2.0.0)
  ([#19](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/19),
  [`1b68d33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1b68d33188afdc14eadf5a3b0a044eb62ce3865b))

### Breaking Changes

- Subpackage environment variables are renamed to a nested schema (TOP_K -> RETRIEVAL__TOP_K,
  CHUNK_SIZE -> CHUNKING__CHUNK_SIZE, EMBED_CONCURRENCY -> INGESTION__EMBED_CONCURRENCY, and so on).
  Startup fails naming the replacement rather than silently ignoring an old name. The v1 import
  paths (rag_mcp.server, rag_mcp.cli, rag_mcp.ingestion, rag_mcp.readers and the rest) are removed.
  Custom profile YAML must be converted to nested blocks. ChromaDB collections, CLI commands and MCP
  tool signatures are unchanged; rollback is code-only. Migration table in
  docs/adr/037-architecture-v2-conformance.md.


## v1.8.0 (2026-06-23)

### Features

- Make liteparse a core dependency
  ([`7eec00e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7eec00e918f875b48399689a84c842391e1b0ec4))


## v1.7.0 (2026-06-23)

### Features

- Flip PDF_READER default to auto (LiteParse when installed)
  ([`4fbff75`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4fbff755473730d49cd4cec472563ce32929ad81))


## v1.6.0 (2026-06-23)

### Bug Fixes

- **exp11**: _parent_id reads dict source, not object metadata
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

- **exp11**: JSON-encode section_bbox for ChromaDB compatibility
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

### Features

- Add pluggable PDF reader factory with LiteParse adapter
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

- Use LiteParse as pluggable PDF reader (gated by Experiment 11)
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

### Performance Improvements

- **reranker**: 10x speedup via CoreML, batching, shorter sequences
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))


## v1.5.3 (2026-06-20)

### Bug Fixes

- **ci**: Fetch full history in release checkout to fix exit 128
  ([`f4d7a9e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/f4d7a9e32a480f781ea8d802d5b49e7cd155717e))


## v1.5.2 (2026-06-20)

### Bug Fixes

- **graphify**: Remove echo banner injection from plugin
  ([`11b66d4`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/11b66d4c361c6f88c166dcc988163faea367ef75))


## v1.5.1 (2026-06-20)

### Bug Fixes

- **reranker**: Guard version regex against ReDoS on digit-only tokens
  ([#6](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/6),
  [`2e5cde9`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2e5cde9ff64a10967191fffb6c3b648b9be193bf))


## v1.5.0 (2026-06-20)

### Bug Fixes

- **test**: Update chunk-overlap default test for ADR-019 reranker default-off
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))

### Features

- **reranker**: Disable reranker by default after Experiment 10
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))

- **reranker**: Implement semantic/technical reranker policy resolver
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))


## v1.4.0 (2026-05-31)

### Features

- **hybrid**: Ship opt-in hybrid retrieval and archive follow-up reranker work
  ([`e3a506f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e3a506f6a6161f557a334d7e42f30a1b74b48006))


## v1.3.0 (2026-05-29)

### Features

- **retrieval**: Promote balanced defaults
  ([`183734d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/183734dbf25938e9db3a154e561da22545491f62))


## v1.2.0 (2026-05-29)

### Features

- **ingestion**: Markdown-aware chunking and overlap bump
  ([`0b91d03`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/0b91d036369e2fbac438ac636eff2f98c81f34ae))

- **retrieval**: Improve markdown retrieval quality
  ([`e963046`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e9630467491d8a3520a7cf736c87be7d27bd7b27))

- **retrieval**: Query embedding cache and configurable rerank pool
  ([`abea2b5`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/abea2b52dbab04003d6a93e80eace0b5c7ea0990))


## v1.1.0 (2026-05-27)

### Bug Fixes

- Offload keyword extraction to thread + large corpus experiment replication
  ([`735ef52`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/735ef52491bd879951ff8ce923ec7980f49f5e58))

### Features

- Expose metadata_filter on MCP search and harden Ollama metadata extraction
  ([`30ccb2d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/30ccb2d624a9da428d3483a35f4e44cb55f194d5))


## v1.0.0 (2026-05-25)

### Features

- Implement archived OpenSpec maintenance changes
  ([`1be0e73`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1be0e739042f2dd812feaa51a1e4c58cf18eb30c))

### Breaking Changes

- Remove rag-mcp ingest --workers/-w, INGEST_WORKERS, and the workers parameter from
  ingest_path_async(). Use EMBED_CONCURRENCY and EMBED_BATCH_SIZE for ingestion throughput tuning.


## v0.1.1 (2026-05-21)

### Bug Fixes

- **ci**: Disable ANSI colour codes in test runner
  ([`bf2a275`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/bf2a2754e6106b090773cc6eebf67b1330c43980))

- **ci**: Skip build in release action (no uv in Docker container)
  ([`03d6754`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/03d67545536fda8d63c034bc1f080ef8d467225c))


## v0.1.0 (2026-05-21)

### Features

- make ingest path async end-to-end
- add document deletion, multi-collection support, and metadata extraction
- add file watcher for automatic document ingestion
- add per-file tracking, concurrent embedding, reports, and benchmark
- add Typer CLI with ingest, search, list commands and parallel ingestion
- shared config module, threshold scaling, reranker flatten fix
- initial RAG MCP server with testing framework

### Bug Fixes

- correct metadata extraction degradation ladder and strip LLM output noise
- replace real user paths with generic placeholders in README
