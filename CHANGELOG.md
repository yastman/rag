# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.14.0](https://github.com/yastman/rag/compare/v2.13.0...v2.14.0) (2026-01-28)


### Features

* **cache:** optimize semantic cache for Russian language ([f6a3bd8](https://github.com/yastman/rag/commit/f6a3bd804c52330863b65905bb22f33ef86bc151))
* **renovate:** add Renovate Bot for Docker image auto-updates ([#10](https://github.com/yastman/rag/issues/10)) ([e90cda9](https://github.com/yastman/rag/commit/e90cda95b25c98a8dacbd92c8f6568aac37d1b47))


### Bug Fixes

* **metrics:** use relative import for config_snapshot ([91e6280](https://github.com/yastman/rag/commit/91e62804ea301d3f58f208884bfd82a607f78eb5))
* **otel:** add missing methods and fix test mocking ([13bd5da](https://github.com/yastman/rag/commit/13bd5dae780ef1752dc510016e08bb382b82d6bc))
* **renovate:** enable default mode to create Issues and PRs ([d8cbc92](https://github.com/yastman/rag/commit/d8cbc92e6aba45cf15c8c1f70c875854ea29fe4e))
* **renovate:** simplify config, remove problematic regex rules ([6c30d52](https://github.com/yastman/rag/commit/6c30d52b2054a6afed08d483bb29067dc84b6755))
* **tests:** correct distance filter test expectations ([f9ab3a6](https://github.com/yastman/rag/commit/f9ab3a6d73da3a77482c7de7b8ec3395fef05feb))
* **tests:** correct price filter test expectations ([2c9745d](https://github.com/yastman/rag/commit/2c9745d509d94be0fd4709be02145ca85456ebd5))
* **tests:** use pytest.approx for floating-point comparison ([d5b666a](https://github.com/yastman/rag/commit/d5b666ac71777d3326b5106582f633b8339cc725))


### Documentation

* add dependency-updates skill design ([ff7bf36](https://github.com/yastman/rag/commit/ff7bf36327eb03ba15c58dada1c060bd1889d9ff))
* add GitHub Issues task management plan ([48b0fa0](https://github.com/yastman/rag/commit/48b0fa0e9ba923b0115292eff96b114a88ceccf3))
* add parallel workers guide and superpowers skills to CLAUDE.md ([02cc33e](https://github.com/yastman/rag/commit/02cc33ec779daaf26854be49598667d2e2f1cb49))
* add README indexes for all modules + Docker documentation ([ecee33d](https://github.com/yastman/rag/commit/ecee33dbdfb363d15b5e68f8f885e2845808be59))
* **claude:** add GitHub Issues task management section ([cc24186](https://github.com/yastman/rag/commit/cc24186ec41a502d06db6ec0fc7fbaea02bb8cfd))
* **claude:** add UserBaseVectorizer documentation ([2bb930a](https://github.com/yastman/rag/commit/2bb930a530a1a8521f7e1f374870b019aa995e6e))
* consolidate documentation structure ([0b53e6a](https://github.com/yastman/rag/commit/0b53e6a1a66f5cbb27958c53d9d8c985c08f6aaa))
* mark Track 1 test fixes complete ([48c0f9b](https://github.com/yastman/rag/commit/48c0f9b534473702155ebd1846b469bcfa96c350))
* **todo:** add issue references and backlog pointer ([8957c47](https://github.com/yastman/rag/commit/8957c47ba0b444fac0010684565d1bc3c430a4bd))
* update for v2.13.0 - docs system complete, start quantization A/B ([3d97fa0](https://github.com/yastman/rag/commit/3d97fa0bf9b3515e2d8636c51fc883f0b3f279e1))
* update PIPELINE_OVERVIEW.md to v2.13.0 ([9c3cb98](https://github.com/yastman/rag/commit/9c3cb989022c6a029d3b70a96aa269a19e02d1d4))

## [2.13.0](https://github.com/yastman/rag/compare/v2.12.0...v2.13.0) (2026-01-26)


### Features

* add BGE-M3 API service for local development ([320a518](https://github.com/yastman/rag/commit/320a518b4cee8f5426f687721f2d5c995784bc4b))
* add BM42 sparse embedding service (Docker) ([3dac4be](https://github.com/yastman/rag/commit/3dac4becbc16825e2676f2da7f1f0b74e4ce20d9))
* add complete dev stack for local development ([e9d4dfe](https://github.com/yastman/rag/commit/e9d4dfe78061ac94df752b0bcb08d17a89db1c2a))
* add CSV row-based chunking for structured data ([853946e](https://github.com/yastman/rag/commit/853946e3c6b5a174468db8e5318ffffd04b1a837))
* Add CSV to Qdrant indexer with comprehensive pipeline documentation ([cdd45d9](https://github.com/yastman/rag/commit/cdd45d9bf628745b67bfe256c53e437e1a713bbc))
* add local development and deploy commands to Makefile ([ce81ca5](https://github.com/yastman/rag/commit/ce81ca5c73fac06373f828d9f32678c58167e93c))
* add local development Docker Compose configuration ([b0c7c00](https://github.com/yastman/rag/commit/b0c7c0065b74f4058af292371e3413de99b87405))
* Add pre-commit and pre-push hooks with Git workflow documentation ([dc43272](https://github.com/yastman/rag/commit/dc43272baa2a128c1b3398dbdf34bcd0807ea800))
* add Qdrant and Redis setup scripts with documentation ([5b450ea](https://github.com/yastman/rag/commit/5b450eabfbe81b8c3f830957f36349f9529f99a5))
* add server deployment configuration (systemd, sudoers) ([c53977b](https://github.com/yastman/rag/commit/c53977bc1a76cd96a71c980cecfcde631e4d1c28))
* add structured metadata for CSV filtering ([08d7a29](https://github.com/yastman/rag/commit/08d7a292564ef370c2a2ed30e499b0882ba8f9c3))
* add unified VoyageService with tenacity retries ([3f6e0f6](https://github.com/yastman/rag/commit/3f6e0f603b5e34f00859f5156154166f9f7b3d28))
* apply Qdrant best practices for resource optimization ([95f5bad](https://github.com/yastman/rag/commit/95f5bade2b90516cd1a2f9b72a3b2075342c3778))
* **bot:** add Markdown formatting for responses ([6590acf](https://github.com/yastman/rag/commit/6590acf511b7a239a31074910b2ecf1f44f9c820))
* **bot:** add QdrantService, BM42 sparse embedder, and _get_sparse_vector ([f56502b](https://github.com/yastman/rag/commit/f56502bab0df994696a382f245615dde98b15cd0))
* **bot:** implement hybrid RRF search with MMR diversity ([a478091](https://github.com/yastman/rag/commit/a47809114ae317c0a9479796780eff7617d31c18))
* **cache:** add RedisVL filterable_fields and native EmbeddingsCache ([5303989](https://github.com/yastman/rag/commit/5303989157b0cb7980ffadf0f28918558614c6aa))
* **cache:** add SemanticMessageHistory for conversation context ([ee674ea](https://github.com/yastman/rag/commit/ee674ea5e1b281f8fd02befa68418fa649fcb691))
* **cache:** add user-base service for semantic cache embeddings ([b282af2](https://github.com/yastman/rag/commit/b282af2bcfd8d4716dd91e1f184619358875b2ab))
* **cache:** implement RerankCache for Voyage API results ([6493c2e](https://github.com/yastman/rag/commit/6493c2eb051fff65d4af5db7b5e62666cae71cbd))
* **cache:** migrate SemanticCache to VoyageAITextVectorizer ([890a9bb](https://github.com/yastman/rag/commit/890a9bb2898a1d6d5c00fcc3f19c395c4b4a7d17))
* **cesc:** add CESC configuration settings ([cd3bd07](https://github.com/yastman/rag/commit/cd3bd0738633b70bbd6aca7ca6667380213e2a75))
* **cesc:** add CESCPersonalizer for cache response personalization ([be5fecd](https://github.com/yastman/rag/commit/be5fecd0ffb4c17a07927fb030378963f9717ec9))
* **cesc:** add UserContextService with preference extraction ([c1473bb](https://github.com/yastman/rag/commit/c1473bb2e13948a33d01518a2013465db530e97d))
* **cesc:** integrate CESC into PropertyBot query handling ([1713fe5](https://github.com/yastman/rag/commit/1713fe5b2c2859d24339acfcc8012cb80b98852f))
* complete local dev setup with Qdrant+Redis+BGE-M3+Docling ([79047ac](https://github.com/yastman/rag/commit/79047ac6a5891825ec419dc2eb78542867ce600b))
* complete local project setup + Cerebras GLM-4.7 integration ([a49a46c](https://github.com/yastman/rag/commit/a49a46cc7043f091742dbcd2b3fcc30c6c8fef6c))
* complete Phase 2 - voyage-4-large reindexing ([573d583](https://github.com/yastman/rag/commit/573d5835e78eef6136cd3b7bd1a3ff986e123e7e))
* complete production-ready ML platform integration plan + Phase 1-2 implementations ([e5aa92f](https://github.com/yastman/rag/commit/e5aa92f6bbbe185edd20768344c328e4ce8d3b07))
* **config:** add Voyage AI configuration settings ([ea89668](https://github.com/yastman/rag/commit/ea896689284e8c37f61ca57371b2aac42a1b77e7))
* Configure Redis semantic cache for Docker environment ([39051e9](https://github.com/yastman/rag/commit/39051e9821ed9a7078d12ec05b24525d18ea29f3))
* enable sparse vectors in HybridRRFSearchEngine ([e59c0ae](https://github.com/yastman/rag/commit/e59c0ae87a6ebf3a97fdb05ff1e5f80f2ea88823))
* export VoyageService from services module ([c46f968](https://github.com/yastman/rag/commit/c46f9687932ca21ab1839adf514d56beff5a79ca))
* **filter:** improve price extraction ([e9c80f1](https://github.com/yastman/rag/commit/e9c80f1c7608a7ad1289d3971b9b68cba40b26b5))
* implement production ML platform - Week 1, 2, 3 complete ([d07d421](https://github.com/yastman/rag/commit/d07d4219d8af7640b53035d1fde99d5f48e25d81))
* implement semantic cache with Redis Vector Search ([5472c88](https://github.com/yastman/rag/commit/5472c883e11c3e9484cf692b8040eaf0900e31cf))
* implement Variant A - complete BGE-M3 + ColBERT rerank ([a16f5d6](https://github.com/yastman/rag/commit/a16f5d6140ac1edac2dbac52e157a9d1d6ff42b5))
* implement Variant B (DBSF + ColBERT) with A/B testing ([5443da3](https://github.com/yastman/rag/commit/5443da351afd6418fa85e578b04640adb49b7d5b))
* **ingestion:** add Contextual Retrieval pipeline for VTT subtitles ([6b8d6cf](https://github.com/yastman/rag/commit/6b8d6cf4fb8f50b0d61364427efddc055f16758b))
* **llm:** add generate() method for CESC preference extraction ([e80be53](https://github.com/yastman/rag/commit/e80be538ba75576fb56c14bfc394c5bd521d9c25))
* optimize RAG ingestion pipeline (Nov 2025) ([bf6030e](https://github.com/yastman/rag/commit/bf6030ef0a5623046a2f92f558273a191ae2fa9e))
* **phase1:** complete critical security and performance fixes ([29b900b](https://github.com/yastman/rag/commit/29b900b2404388aad815182e6c1a521f55f4a6fd))
* **phase2:** production optimizations - singleton, memory, streaming ([5bf98a2](https://github.com/yastman/rag/commit/5bf98a296d552ebbcc147c97afc80a822b1a7b79))
* **qdrant:** add binary quantization support for 40x faster search ([b3549d7](https://github.com/yastman/rag/commit/b3549d7cb9831b3386f67b01a41ceb819af38ada))
* **qdrant:** add QdrantService with Query API, Score Boosting, MMR ([0ef1389](https://github.com/yastman/rag/commit/0ef138964e44b2b3518ab12150ffff49a6030a93))
* **qdrant:** add quantization_ignore param for A/B testing ([320ddef](https://github.com/yastman/rag/commit/320ddefac772f3bc691ce0930635f4ba4e475130))
* **qdrant:** switch from Scalar INT8 to Binary Quantization ([8d935fb](https://github.com/yastman/rag/commit/8d935fb29b9f8627763d1eb5202fb391c5ab8aaf))
* **qdrant:** wire QuantizationSearchParams for A/B testing ([7ec8297](https://github.com/yastman/rag/commit/7ec8297c91c22dca9462c11ccae395e2d43ecf20))
* **redis:** configure 512MB maxmemory with allkeys-lfu ([4a3c78c](https://github.com/yastman/rag/commit/4a3c78c0126f6b028423c4698edf42299c60c383))
* **rerank:** add VoyageRerankerService for result reranking ([76df79a](https://github.com/yastman/rag/commit/76df79af8293adec09234ed4a8b8acea204ef21e))
* **resilience:** add graceful degradation and structured logging ([8c86472](https://github.com/yastman/rag/commit/8c8647231e03f1a364f9b0f4e96f95139030c279))
* **retriever:** add HybridRetrieverService with RRF fusion ([2e3ee5d](https://github.com/yastman/rag/commit/2e3ee5d9e411353f1b0fc3a49648295ef15c1f4e))
* **search:** add lexical_weights_to_sparse helper for SDK migration ([6b843f8](https://github.com/yastman/rag/commit/6b843f8e7cebfc6d07e2d55ba10dd1ec8881f0e5))
* **services:** export Phase 2 Voyage services ([939a79a](https://github.com/yastman/rag/commit/939a79ac2e6017a9466c9165d50b317ca6ffc520))
* **services:** export VoyageClient and QueryPreprocessor ([f0a4ba7](https://github.com/yastman/rag/commit/f0a4ba74cc82562f73d75fbd2678b9d3b32c1f39))
* smart Ukrainian legal document detection for DOCX files ([5a465b3](https://github.com/yastman/rag/commit/5a465b39a1c21604557f634654c8b0c073af930e))
* switch bot.py to unified VoyageService with voyage-4 models ([33a1572](https://github.com/yastman/rag/commit/33a15726dfc7b618e55bc007da61c2456279dc6d))
* universal document indexer for n8n/LangChain ([0a736ab](https://github.com/yastman/rag/commit/0a736abb82133f7b344ff5586d38915765f44050))
* update indexer to n8n LangChain compatible format ([4917bf8](https://github.com/yastman/rag/commit/4917bf8bd682148ae4187b328abc6ea2cfad1788))
* update voyage_indexer to use VoyageService with voyage-4-large ([0230c16](https://github.com/yastman/rag/commit/0230c16137a35677e3bbb9b2b5350127a4841cfc))
* upgrade Redis to Redis Stack for vector search support ([ff8d7fe](https://github.com/yastman/rag/commit/ff8d7fe4c8dd2810c7d25e3f111e7c38a614fa8f))
* upgrade to BGE-M3 multi-vector embeddings with optimizations ([5e39314](https://github.com/yastman/rag/commit/5e393146b1bb9f35e983eefce80a657034a46ac3))
* upgrade to BM42 sparse embeddings for improved RAG performance ([1080609](https://github.com/yastman/rag/commit/108060945c2ba44926639bf5497febd11d061568))
* **ux:** integrate streaming, conversation memory, and reranking ([a0728d5](https://github.com/yastman/rag/commit/a0728d51336b0446fe6bfee2ad42167410e397a9))
* **voyage:** add Matryoshka embedding support (Phase 4) ([e35ab72](https://github.com/yastman/rag/commit/e35ab72947ae995fae311569177276201c9b9526))
* **voyage:** add VoyageClient with retry logic and singleton pattern ([32e2164](https://github.com/yastman/rag/commit/32e216492fb8001ef72c77d8b055aa0e88f1f1d4))


### Bug Fixes

* **bot:** add missing cachetools dependency ([77472f0](https://github.com/yastman/rag/commit/77472f02c0bf9111b3934aa69a594e95a57385ea))
* **bot:** add QdrantService cleanup in stop method ([d20671a](https://github.com/yastman/rag/commit/d20671a5bafed460c3183f360be95c51c5365343))
* **bot:** correct BGE-M3 API default port 8001 -&gt; 8000 ([e6e3e0b](https://github.com/yastman/rag/commit/e6e3e0b86ed078188a670830dbdc9378537feaf0))
* **bot:** prevent duplicate edit errors in streaming ([3ba4f68](https://github.com/yastman/rag/commit/3ba4f68629326a6df78c8fa55889688a23ebc45c))
* **bot:** use contextual_bulgaria collection by default ([5ab2c03](https://github.com/yastman/rag/commit/5ab2c03584e93bbb7e59396b5994aa1d27147de9))
* **cache:** use 'content' param for EmbeddingsCache API ([f36e1ae](https://github.com/yastman/rag/commit/f36e1ae38b5e437e47a643341119d19fa44c68b1))
* **cesc:** wire up config fields and add cesc_enabled check ([6c8a9c3](https://github.com/yastman/rag/commit/6c8a9c3f983894360b6b1001b049fd3779676531))
* clean up ML platform plan - remove broken code and old sections ([ed953ef](https://github.com/yastman/rag/commit/ed953ef88e4193b3ff9ac40eb6cc5b5b54c447f1))
* correct Qdrant healthcheck endpoint /health -&gt; /healthz ([aca70a1](https://github.com/yastman/rag/commit/aca70a1cc6d0cd64bafce5dcad8e26e76bf6f91b))
* correct service name in release deploy workflow ([9aa21aa](https://github.com/yastman/rag/commit/9aa21aa1e389be3267666922cc76c6b12c152f90))
* handle bytes keys in RediSearch module detection ([15d7956](https://github.com/yastman/rag/commit/15d79565000a4288eb0063794b14923b8dcae473))
* Migrate src/evaluation imports to new config structure ([26a277e](https://github.com/yastman/rag/commit/26a277ea69f66662de86785edb17ea4a41e769d1))
* preserve article_number metadata from chunker in ingestion pipeline ([55f0914](https://github.com/yastman/rag/commit/55f09146816b78e39ac5ed20961b05bf6edfb28d))
* resolve all Ruff linting errors ([97bb7bf](https://github.com/yastman/rag/commit/97bb7bf06efa18e0679a12d151301337169c7f89))
* **retriever:** return None for empty filters ([97134b7](https://github.com/yastman/rag/commit/97134b712269ed67d926803dc3af8f2e18f0305a))
* update all payload access to new format (page_content + metadata) ([edbffa1](https://github.com/yastman/rag/commit/edbffa1d68b197f9f9eb1c58f1ebaf295331e6ca))
* use Modifier.IDF enum for sparse vectors instead of string ([e5adcd5](https://github.com/yastman/rag/commit/e5adcd5dd7ac2097cfb27fabd7b7ad8d0f0b5f85))
* use official MultiVectorConfig for ColBERT instead of dict ([2cf93e6](https://github.com/yastman/rag/commit/2cf93e60c5d1ab8e4b126287f9d8f34a1ba8a035))


### Performance

* **cache:** implement 2026 RAG caching best practices ([93803c5](https://github.com/yastman/rag/commit/93803c5f39b2658ea070cebae035621c1306c843))
* **config:** reduce search_top_k from 30 to 20 for faster retrieval ([17552b9](https://github.com/yastman/rag/commit/17552b95e855189e796d47e66c7f196f3077e383))
* **imports:** add RAG_TESTING flag to skip heavy imports ([2c24c09](https://github.com/yastman/rag/commit/2c24c09e042038a0a7c25446419b6447df6cc03a))
* **indexer:** add ColBERT m=0 optimization ([257d159](https://github.com/yastman/rag/commit/257d159fd46f9fad74c1ae643f2e48f952ea8cd1))
* optimize CI - only install linters, skip tests ([192550e](https://github.com/yastman/rag/commit/192550e6ec4f2ff693d81ec45e2aabd4d85cc4ce))
* **pipeline:** optimize context & add query routing (2026 best practices) ([78c0950](https://github.com/yastman/rag/commit/78c0950f9360814957cfbeeba5d95976c80e9a69))


### Documentation

* add active tasks tracking ([5530d22](https://github.com/yastman/rag/commit/5530d2257d98e5a0bd8b49b1717a085d862223a5))
* Add Azbyka RAG implementation plan 2025 v2 ([4e02017](https://github.com/yastman/rag/commit/4e0201798b05ad470dd2c88b398e2833d16a2230))
* add CESC implementation design plan ([7a55aeb](https://github.com/yastman/rag/commit/7a55aebf7673938a8da98705e604310d5eb4f8b2))
* Add Claude Code CLI as recommended development method ([da994a0](https://github.com/yastman/rag/commit/da994a0af0340a2ba5dbea54f8f85f17b47cf452))
* add Claude Code project brief ([95c77a8](https://github.com/yastman/rag/commit/95c77a882bac6987d52bee24273125e9499a167f))
* add coding standards ([4db6300](https://github.com/yastman/rag/commit/4db6300c0a5955c92dace89b62e86ce160051175))
* add completed tasks history ([1254bf2](https://github.com/yastman/rag/commit/1254bf2bf99d22d93cb0f9b9364055cab872a017))
* add comprehensive caching documentation ([efe5ef1](https://github.com/yastman/rag/commit/efe5ef1f420d573dc13f14c8dced55c2353bebc7))
* add comprehensive Qdrant stack documentation and update pipeline overview ([7a9b13a](https://github.com/yastman/rag/commit/7a9b13acba357a492c59a3a91df6d0b9b642c9c9))
* add comprehensive task allocation and testing plans ([04dacdb](https://github.com/yastman/rag/commit/04dacdbe98efed6d24e2d1e32768b7da658dab11))
* add comprehensive testing design plan ([87c42b2](https://github.com/yastman/rag/commit/87c42b2c2ae94614777cd8c8e3df13495ec6cc04))
* add comprehensive testing implementation plan ([0076630](https://github.com/yastman/rag/commit/00766305ddba02b2f6f4d42b6afab0dc1f1ff714))
* add contributing guide for local development workflow ([853ec23](https://github.com/yastman/rag/commit/853ec232c48d8c293b68c576f6f9cfb766760771))
* add current project state ([f02fe06](https://github.com/yastman/rag/commit/f02fe0687bd62beb58f4538bed1692142fe15fd9))
* add detailed implementation plan for dev workflow ([d4e4ba5](https://github.com/yastman/rag/commit/d4e4ba59a94c8c05cfc2797f2596eabe654fe2d1))
* add dev workflow design for local development and CI/CD ([093d1c5](https://github.com/yastman/rag/commit/093d1c562c02196aefb755a0e30334ab60852903))
* add document indexing tutorial ([fa68e00](https://github.com/yastman/rag/commit/fa68e006d32de497a471bb708adcbaf7a75e082e))
* add first search tutorial ([dec8096](https://github.com/yastman/rag/commit/dec80964ddaced3a6fc488c3ad5e8e92d026f1cf))
* add local setup guide ([f2d418a](https://github.com/yastman/rag/commit/f2d418a8fd35377b78671a2db6a7ad2f3ed7f259))
* add local vs production checklist ([b6262d2](https://github.com/yastman/rag/commit/b6262d20d6af119487da01f62e1e99e3d0d3156b))
* add main navigation index ([9e95a38](https://github.com/yastman/rag/commit/9e95a3872e99007c3e399ba5b8dcde70bfec7cd7))
* add placeholder files for migration ([cd025fe](https://github.com/yastman/rag/commit/cd025fe21c474a087156caf6dffe7d8a5baa507f))
* add production deployment completion plan ([ad33d9e](https://github.com/yastman/rag/commit/ad33d9e678abcb0aa97ce84936be3539acc9a972))
* add QdrantService integration design ([25c244f](https://github.com/yastman/rag/commit/25c244fd59fa3e57ad98c624125ff141b0094d90))
* add QdrantService integration implementation plan ([08e8a79](https://github.com/yastman/rag/commit/08e8a79148e9a1c6bd1fa9c7de9873bf2f93c259))
* Add README for ingestion module with script descriptions ([28b9d6b](https://github.com/yastman/rag/commit/28b9d6b9fc13eb7bbe4849c12bab8260973696e1))
* add SCRIPTS_README.md with detailed description of test scripts ([ff7e712](https://github.com/yastman/rag/commit/ff7e712bfc105572445d7d68f70a85868a3a6ad8))
* Add server-based development workflow guide ([f4ff31e](https://github.com/yastman/rag/commit/f4ff31e48d6945cd78624aef6bff78d6e188db04))
* add smoke/load tests documentation ([46faeed](https://github.com/yastman/rag/commit/46faeed03b8236e16fce809757af85e5589a2904))
* add task backlog ([bec9084](https://github.com/yastman/rag/commit/bec9084b3149f3f1fc48e1d8e6aebd527553d58d))
* add troubleshooting guide ([2e0d392](https://github.com/yastman/rag/commit/2e0d392cbc27a95c9997893eed2e8b9aa3d76973))
* **cesc:** update documentation for CESC v2.9.0 ([ab0a5bf](https://github.com/yastman/rag/commit/ab0a5bf1f243cfa7048219f7f300f1552c27ab99))
* **cesc:** update plan with TDD-style bite-sized tasks ([c605c03](https://github.com/yastman/rag/commit/c605c03e889c694ae84db218adcdc7d57d78fa8a))
* **changelog:** prepare for Release Please (remove Unreleased section) ([726b0b8](https://github.com/yastman/rag/commit/726b0b8ce958289b53132717774b504c888f1bd5))
* **claude:** add Current Sprint section for persistent context ([655ff66](https://github.com/yastman/rag/commit/655ff669ecf1dc3ea903f67d70d7992ed3940e9c))
* **claude:** add smoke/load tests documentation ([5040c8f](https://github.com/yastman/rag/commit/5040c8f8c7a38195c4d49256830e53920305f3ec))
* **claude:** cleanup + add Troubleshooting and API Rate Limits ([145e3c8](https://github.com/yastman/rag/commit/145e3c8124159c8c955f41870ceec9b5daeda8c6))
* **claude:** update Task Management section for new workflow ([7b8f8a7](https://github.com/yastman/rag/commit/7b8f8a73d4678ec23fa13915bd645865e17599f2))
* Create comprehensive README documentation for all modules ([9c2da9f](https://github.com/yastman/rag/commit/9c2da9fd353dd1a5f6125813bd4971a23fd9e7d4))
* Create detailed implementation plan with gap analysis ([5bba59a](https://github.com/yastman/rag/commit/5bba59af5a638cee875dc268b2af92a7a4d3601b))
* create Diátaxis folder structure ([d61c436](https://github.com/yastman/rag/commit/d61c4362c2ee5d3db45db1d369b98df09da194de))
* enhance ML platform integration plan with production requirements ([ebc6ee2](https://github.com/yastman/rag/commit/ebc6ee29cfebd8ebebbe28d8e8b35e857fdda7e2))
* link to new documentation index ([2675471](https://github.com/yastman/rag/commit/2675471ee31070645deeabaec5bfdb6733893b65))
* **plans:** add detailed TDD implementation plan ([3c9ec44](https://github.com/yastman/rag/commit/3c9ec44161fb1c8fb70f86f93c263af3edd67b1a))
* **plans:** add full test coverage design ([e55831e](https://github.com/yastman/rag/commit/e55831e684ff68469cbc8898b8161ace1a48a89b))
* Rewrite README as workflow guide for new Claude sessions ([c820847](https://github.com/yastman/rag/commit/c82084763c27fafb969eaf9da59605c495ac6e99))
* **tests:** add smoke + load tests design ([6945ed8](https://github.com/yastman/rag/commit/6945ed88b1a6d97276d46746686f8d44f3dce344))
* **todo:** reset TODO.md to short format (15 lines) ([60e6a54](https://github.com/yastman/rag/commit/60e6a54bdae30fa5bd3d097af397dd7dbfe1c057))
* Translate all remaining documentation to English ([2ee6e32](https://github.com/yastman/rag/commit/2ee6e32257222186c30aa41d9c1946151fea28c3))
* Translate key documentation files to English ([2c06657](https://github.com/yastman/rag/commit/2c06657d7fe62ca8546436607c0ec0555dfc9460))
* Translate README.md to English ([c570c5b](https://github.com/yastman/rag/commit/c570c5bcd7a4c1a57e802eaa2e92800461823e96))
* update CLAUDE.md and README.md for v2.12.0 SDK migration ([c8cf24d](https://github.com/yastman/rag/commit/c8cf24d7193d6efcdbb6662980cfa31d7df3e122))
* update CLAUDE.md for VoyageService and voyage-4 models ([bfa9f20](https://github.com/yastman/rag/commit/bfa9f202faa30473b66b9fbdcad377ff010b4ea5))
* update CLAUDE.md with 2026 TTFT optimizations ([98189b4](https://github.com/yastman/rag/commit/98189b4f08fcea51560cc92c4267298f52f8fc40))
* update CLAUDE.md with test structure and coverage ([56b3e1d](https://github.com/yastman/rag/commit/56b3e1dcdf1c488adba17f51f1e3664c7fcf51e9))
* update CLAUDE.md with v2.11.0 quantization features ([a047eb1](https://github.com/yastman/rag/commit/a047eb1bd40897991352e45cad96be0376ef3976))
* update documentation for Variant A implementation (v2.2.0) ([f8dc27c](https://github.com/yastman/rag/commit/f8dc27cf3d59b3feccb755a75d0846fb67d4d0c9))
* update documentation with Qdrant configuration fixes ([3385ae9](https://github.com/yastman/rag/commit/3385ae99de92d77c8f874f2a76251750fe694551))
* update for v2.8.0 release - resilience and observability ([3545732](https://github.com/yastman/rag/commit/35457325a1ddf0f6d8c5a5e6f9a2057b55cf90fe))
* update README and CHANGELOG for v2.6.0 release ([050e52f](https://github.com/yastman/rag/commit/050e52f616a616fd6fc629c19d715fdc1962f5bc))
* update README and CHANGELOG for v2.7.0 ([0d8ba01](https://github.com/yastman/rag/commit/0d8ba01720c8763a3c2dacf9a109cfbb57d67235))
* Update README with CSV support and Qdrant Web UI access ([3a928e9](https://github.com/yastman/rag/commit/3a928e9508ce7d5e0dba8a84dec9bff1df5183d1))
* Update repository links and fix dates ([561edf5](https://github.com/yastman/rag/commit/561edf50b9989a2b9abaa227f98a63f9d66bd9f9))
* update ROADMAP with Phase 1 & 2 completion ([4a0df30](https://github.com/yastman/rag/commit/4a0df306d734031cb739fc51ce4fd03c9dcf48bc))
* update TODO and ROADMAP to reflect current state ([01d1d8a](https://github.com/yastman/rag/commit/01d1d8a2b896bf15e88a3f901a90345d37c76f0a))
* update TODO with completed cache bugfixes (v2.9.1) ([825cbdd](https://github.com/yastman/rag/commit/825cbdd820a31ea738e8d319e98a549e52b374bf))
* update TODO, ROADMAP, add VPS_QUICKSTART for server deployment ([0a51b3c](https://github.com/yastman/rag/commit/0a51b3c6616fed862cf85e9de68583f10748343a))
* update TODO.md and ROADMAP.md for CESC v2.9.0 ([0b15871](https://github.com/yastman/rag/commit/0b15871e7f4c47e85559d548b5afd4a32d475ebd))
* **voyage:** add bite-sized implementation plan for Voyage migration ([5e83f09](https://github.com/yastman/rag/commit/5e83f09b038cb20494bf132d98d14fdd696987f5))
* **voyage:** add Voyage Unified RAG implementation plan ([2bf08b5](https://github.com/yastman/rag/commit/2bf08b56105e88a94f4b7a9342f4d3b5458efa77))

## [2.9.0] - 2026-01-21

### ✨ Features
- ✅ **CESC (Context-Enabled Semantic Cache)** - personalized cached responses
  - `UserContextService` - extracts user preferences from queries via LLM
  - `CESCPersonalizer` - adapts cached responses to user context
  - Preferences: cities, budget, property types, rooms
  - Extraction frequency: every 3rd query
  - Storage: Redis JSON with 30-day TTL

### ⚡ Performance
- Cache HIT personalization: ~100ms (vs 2-3s full RAG)
- Lightweight LLM call: ~100 tokens for personalization
- User context stored efficiently in Redis

### 🏗️ Architecture
- New services: `telegram_bot/services/user_context.py`, `telegram_bot/services/cesc.py`
- Configuration: `cesc_enabled`, `cesc_extraction_frequency`, `user_context_ttl`
- Integration: `PropertyBot.handle_query` now personalizes cache hits

### 🧪 Testing
- 33 tests total for CESC components
  - `test_user_context.py` - 19 unit tests
  - `test_cesc.py` - 11 unit tests
  - `test_cesc_integration.py` - 3 integration tests

---

## [2.8.0] - 2025-01-06

### 🛡️ Resilience
- ✅ **Graceful degradation** for all services (zero downtime)
  - Qdrant: Health checks, 5s timeout, empty results on failure
  - LLM: HTTP error handling, fallback answers with search results
  - Redis: Existing error handling improved
- ✅ **Production error handling** - services fail gracefully without crashing

### 📊 Observability
- ✅ **Structured JSON logging** for production
  - JSONFormatter for log aggregation (ELK, Grafana Loki, CloudWatch)
  - Configurable via `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE` env vars
  - StructuredLogger wrapper for contextual logging
  - Third-party logger noise reduction

### 🏗️ Architecture
- Improved service resilience patterns
- Better error propagation and handling
- Production-ready logging infrastructure

---

## [2.7.0] - 2025-01-06

### ✨ Features
- ✅ **Streaming LLM responses** integrated in bot (real-time token display)
- ✅ **Conversation memory** enabled for multi-turn dialogues
- ✅ **Cross-encoder reranking** for +10-15% accuracy improvement
- ✅ Added `/clear` command to clear conversation history
- ✅ Added `/stats` command to view cache performance

### ⚡ Performance
- Cross-encoder reranking: ms-marco-MiniLM-L-6-v2 (CPU-optimized)
- Rerank latency: ~50-100ms for top-5 results
- Streaming: First tokens in 0.1s (10x UX boost)

### 🏗️ Architecture
- Created `src/retrieval/reranker.py` module
- Singleton pattern for cross-encoder (save memory)
- Graceful fallback: streaming → non-streaming on error

---

## [2.6.0] - 2025-01-06

### 🔒 Security
- ✅ Removed exposed API keys from README.md (#1.1)
- ✅ Replaced hardcoded secrets with placeholders

### ⚡ Performance
- ✅ Migrated from `requests` to `httpx.AsyncClient` in search engines (#1.2)
- ✅ Fixed blocking async calls in `pipeline.py` (#1.4)
- ✅ Implemented BGE-M3 singleton pattern - **saved 4-6GB RAM** (#2.1)
- ✅ Added LLM streaming responses - **10x UX improvement** (0.1s TTFB) (#2.3)

### ✨ Features
- ✅ Added `ThrottlingMiddleware` for rate limiting (1.5s window)
- ✅ Added `ErrorHandlerMiddleware` for centralized error handling
- ✅ Implemented conversation memory in Redis (multi-turn dialogues)
- ✅ Created `src/models/` module for shared model instances

### 📦 Dependencies
- ✅ Completed `requirements.txt` with missing packages (#1.3):
  - FlagEmbedding>=1.2.0
  - sentence-transformers>=2.2.0
  - anthropic>=0.18.0
  - openai>=1.10.0
  - groq>=0.4.0
  - transformers>=4.30.0
  - mlflow>=2.22.1
  - ragas>=0.2.10
  - langfuse>=3.0.0
  - datasets>=3.0.0
  - cachetools>=5.3.0

### 📝 Documentation
- ✅ Created comprehensive ROADMAP.md (16 tasks, 4 phases)
- ✅ Created CHANGELOG.md (this file)
- ✅ Created TODO.md for daily task tracking
- ✅ Created TASK_MANAGEMENT_2025.md
- ✅ Updated .claude.md with project context

### 🏗️ Architecture
- ✅ Added singleton pattern for embedding models
- ✅ Integrated production-ready middleware from templates
- ✅ Implemented async streaming for LLM responses

---

## [2.5.0] - 2025-11-05

### ✨ Added
- **Semantic Cache Architecture** - 4-tier caching with Redis Vector Search
  - Tier 1: Semantic cache with KNN (COSINE similarity, threshold 0.85)
  - Tier 1: Embeddings cache (30 days TTL, 1000x speedup)
  - Tier 2: Query analyzer cache (24h TTL)
  - Tier 2: Search results cache (2h TTL)
- Different query phrasings now trigger cache HIT
- Cache performance: 1-5ms latency for semantic matching

### 📝 Documentation
- Added `CACHING.md` - Comprehensive caching architecture guide
- Added `SEMANTIC_CACHE_COMPARISON.md` - Comparison of semantic cache approaches

### ⚡ Performance
- Semantic cache hit rate: 70-80%
- Cost savings: 90% (LLM call reduction)
- Cache query latency: 1-5ms

---

## [2.4.0] - 2025-11-05

### ✨ Added
- **Universal Document Indexer** - CLI tool for indexing multiple formats
  - Supports: PDF, DOCX, CSV, XLSX in single command
  - New script: `simple_index_test.py`
- Demo files organized in `data/demo/`
  - `demo_BG.csv` - 4 Bulgarian property listings
  - `info_bg_home.docx` - Company contact information

### 🐛 Fixed
- Fixed Docling parser configuration issues
- Improved CSV to Qdrant indexing reliability

### 📝 Documentation
- Added usage examples for universal indexer
- Documented demo file structure

---

## [2.3.1] - 2025-11-04

### ✨ Added
- **CSV Support** - Direct CSV → Qdrant indexer
  - New script: `src/ingestion/csv_to_qdrant.py`
  - Structured metadata extraction for filtering
- Qdrant Web UI access documentation

### 📝 Documentation
- Added `PIPELINE_OVERVIEW.md` - Complete system architecture
- Documented Qdrant collections:
  - `legal_documents` - 1,294 points (Ukrainian Criminal Code)
  - `bulgarian_properties` - 4 points (demo CSV)
- Added Qdrant Web UI access instructions

### 🔧 Configuration
- Documented Qdrant API key usage
- Added collection statistics

---

## [2.3.0] - 2025-10-30

### ✨ Added
- **Variant B: DBSF + ColBERT** Search Engine
  - Distribution-Based Score Fusion (DBSF) algorithm
  - Statistical score normalization
  - 7% faster than RRF variant (0.937s vs 1.0s)
- **A/B Testing Framework**
  - Compare Variant A (RRF) vs Variant B (DBSF)
  - MLflow experiment tracking
  - Automated metrics calculation

### ⚡ Performance
- Variant B latency: ~0.937s
- Top result agreement with Variant A: 66.7%
- Expected Recall@1: ~94-95%

### 📝 Documentation
- Added Variant A/B comparison guide
- Documented DBSF fusion algorithm
- Added A/B testing instructions

---

## [2.2.0] - 2025-10-30

### ✨ Added
- **Variant A: RRF + ColBERT** (Default Search Engine)
  - 3-Stage Pipeline:
    1. Prefetch: Dense (100) + Sparse BM42 (100)
    2. Fusion: Reciprocal Rank Fusion (RRF)
    3. Rerank: ColBERT MaxSim
  - BM42 sparse vectors (better than BM25 for short chunks)
  - Server-side ColBERT reranking in Qdrant

### ⚡ Performance
- Recall@1: ~95% (improved from 91.3% baseline)
- NDCG@10: ~0.98
- Latency: ~1.0s
- +9% Precision@10 with BM42 vs BM25

### 🔧 Changed
- Made Variant A default search engine
- Upgraded Qdrant to v1.15.4 for BM42 support

---

## [2.1.0] - 2025-10-30

### ✨ Added
- **ML Platform Integration**
  - MLflow experiment tracking (port 5000)
  - Langfuse LLM tracing (port 3001)
  - RAGAS evaluation framework
  - OpenTelemetry distributed tracing
- **2-Level Redis Cache**
  - Level 1: Embeddings cache (7 days TTL)
  - Level 2: Search results cache (1 hour TTL)
- **Model Registry**
  - Staging → Production workflow
  - Version tracking
  - Rollback capability
- **Security Features**
  - PII redaction (Ukrainian patterns)
  - Budget guards ($10/day, $300/month)
  - Rate limiting framework

### 📝 Documentation
- Added `src/evaluation/README.md` - MLflow/Langfuse guide
- Added `src/cache/README.md` - Caching architecture
- Added `src/governance/README.md` - Model registry
- Added `src/security/README.md` - Security features

### 🔧 Infrastructure
- Prometheus metrics (port 9090)
- Grafana dashboards (port 3000)

---

## [2.0.0] - 2025-10-25

### ✨ Added
- **BGE-M3 Multi-Vector Embeddings**
  - Dense vectors (1024-dim) for semantic search
  - Sparse vectors (BM25) for keyword matching
  - ColBERT multivectors for token-level reranking
- **Qdrant Optimizations**
  - Scalar Int8 quantization (4x compression, 0.99 accuracy)
  - ~75% RAM savings (original vectors on disk)
  - HNSW optimization (m=16, ef_construct=200)
  - Batch processing (32 embeddings, 16 documents)

### ⚡ Performance
- Recall@10: 0.96
- NDCG@10: 0.98
- RAM savings: ~75%
- Query latency: < 1.5s

### 🔄 Changed
- Upgraded from single-vector to multi-vector approach
- Migrated from BM25 to BM42 sparse vectors

### 📝 Documentation
- Added `QDRANT_STACK.md` - Detailed configuration guide

---

## [1.0.0] - 2025-10-15

### ✨ Initial Release
- Basic RAG pipeline with dense vectors
- PDF document parsing (PyMuPDF)
- Baseline search engine (Recall@1: 91.3%)
- Qdrant vector database integration
- Basic caching layer

### 📦 Core Features
- Document chunking (512 chars, 128 overlap)
- Semantic search with embeddings
- LLM integration (Claude, OpenAI, Groq)
- REST API endpoints

### 📝 Documentation
- Initial README.md
- Basic setup instructions

---

## Legend

### Types of Changes
- `Added` - New features
- `Changed` - Changes in existing functionality
- `Deprecated` - Soon-to-be removed features
- `Removed` - Removed features
- `Fixed` - Bug fixes
- `Security` - Security fixes

### Priority Icons
- 🔴 **CRITICAL** - Security or data loss issues
- 🟠 **HIGH** - Performance or functionality blockers
- 🟡 **MEDIUM** - Important but not blocking
- 🟢 **LOW** - Nice-to-have improvements

### Category Icons
- ✨ Features
- 🐛 Bug Fixes
- ⚡ Performance
- 🔒 Security
- 📝 Documentation
- 🔧 Configuration
- 📦 Dependencies
- 🔄 Changes
- ❌ Removals

---

## Release Schedule

- **v2.6.0** (Critical Fixes) - Target: 2025-01-08 (2 days)
- **v2.7.0** (High Priority) - Target: 2025-01-15 (1 week)
- **v3.0.0** (Production Ready) - Target: 2025-01-24 (2 weeks)
- **v3.1.0** (Nice-to-have) - Target: 2025-02-10 (4 weeks)

---

## Versioning Strategy

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0) - Breaking API changes
- **MINOR** (x.X.0) - New features (backward compatible)
- **PATCH** (x.x.X) - Bug fixes (backward compatible)

### Version Bumping Rules

- Security fixes → PATCH
- Bug fixes → PATCH
- New features → MINOR
- Performance improvements → MINOR (if significant) or PATCH
- Breaking changes → MAJOR
- Critical infrastructure changes → MAJOR

---

## How to Update This File

1. **For developers:**
   ```bash
   # Add your changes under [Unreleased]
   # Use checkbox format: - [ ] Your change description
   ```

2. **For releases:**
   ```bash
   # Move items from [Unreleased] to new version section
   # Update version number and date
   # Mark checkboxes as completed: - [x]
   ```

3. **Commit format:**
   ```bash
   git commit -m "docs(changelog): add v2.6.0 release notes"
   ```

---

**Maintained by:** Project Team
**Last updated:** 2025-01-06
**Format:** [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/)
