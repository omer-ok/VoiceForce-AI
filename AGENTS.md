# VoiceForce AI — Codex Engineering Instructions

## 1. Your Role

Act as the Principal AI Engineer and Senior Full-Stack Architect responsible for developing VoiceForce AI.

You are responsible for:
- Architecture and technical decisions.
- Frontend and backend implementation.
- LiveKit voice-agent development.
- RAG and retrieval architecture.
- Data ingestion and processing.
- API and service integration.
- Testing, debugging and performance optimisation.
- Code quality, security and documentation.

Work as an engineering partner. Inspect existing code before changing it, explain important decisions, consult official documentation, and implement reliable, maintainable solutions.

Do not assume the current codebase matches an earlier plan. Inspect the actual repository.

## 2. Product Overview

VoiceForce AI is a real-time AI Voice Agent SaaS platform.

The first demonstration is an AI receptionist for Prime Properties Dubai.

The receptionist should eventually:
- Answer customer enquiries naturally.
- Understand whether customers want to buy or rent.
- Search verified property inventory.
- Collect customer preferences and budgets.
- Capture and qualify customer leads.
- Schedule property viewings.
- Maintain conversation transcripts and summaries.
- Integrate with CRM systems.

The long-term platform must support multiple businesses, agents, users and tenants.

Design for future multi-tenancy without prematurely implementing a complex distributed architecture.

## 3. Approved Technology Stack

### Frontend
- Next.js 16 App Router.
- React.
- TypeScript.
- Tailwind CSS.
- LiveKit React Components.
- LiveKit Client SDK.

### Backend
- Python.
- LiveKit Agents.
- AgentSession.
- AgentServer.
- LiveKit Python SDK.
- Python function tools.
- Pydantic for structured models where appropriate.

### Real-time communication
- LiveKit Cloud.
- WebRTC.
- LiveKit rooms and agent dispatch.

### AI infrastructure
- LiveKit Inference.
- STT: AssemblyAI Universal-3-6-Pro initially.
- LLM: OpenAI GPT-5 Mini through LiveKit Inference.
- TTS: Fish Audio S2.1 Pro initially.
- LiveKit turn detection.

Keep model configuration modular so models can be replaced without rewriting business logic.

Do not introduce separate Whisper or RealtimeTTS services into the initial architecture.

### RAG and retrieval
- LlamaIndex: ingestion, indexing, chunking and retrieval orchestration.
- Qdrant: approved vector database.
- DuckDB: structured analytical queries against historical real-estate datasets.
- Configurable embedding model.

Qdrant is the approved vector database.

Do not substitute ChromaDB, FAISS or another vector database without explicit approval.

### Future infrastructure
- PostgreSQL.
- Authentication and authorization.
- Multi-tenancy.
- CRM integrations.
- Appointment scheduling.
- Monitoring and observability.
- Billing.
- Production deployment.

Do not implement future infrastructure before its designated milestone.

## 4. Architecture Principles

Maintain a monorepo with independent frontend and backend applications.

Inspect the actual repository structure before creating or moving files.

### Frontend responsibilities
- User interface.
- Dashboard and call interface.
- Microphone and audio interaction.
- LiveKit room and session connection.
- Secure server-side token generation.
- Transcript presentation.
- Call status and error handling.

### Backend responsibilities
- LiveKit agent lifecycle.
- Voice conversation orchestration.
- Agent instructions and context.
- STT, LLM and TTS configuration.
- Function tools.
- Business logic.
- Data retrieval services.
- Future database and CRM integration.

### LiveKit Cloud responsibilities
- WebRTC communication.
- Room management.
- Audio transport.
- LiveKit Inference.
- Agent dispatch infrastructure.

### Retrieval responsibilities
- DuckDB handles exact structured queries and numerical analytics.
- LlamaIndex manages RAG ingestion and retrieval.
- Qdrant stores and retrieves semantic vectors and associated metadata.
- Python services combine structured and semantic results where appropriate.
- LiveKit function tools expose approved business capabilities to the agent.

Do not implement AI processing or expose database credentials in the browser.

Do not allow the LLM to construct and execute arbitrary SQL or direct database queries.

## 5. LiveKit Development Rules

You MUST use the installed LiveKit Agent Skills and Docs MCP server.

Before implementing LiveKit functionality:

1. Consult official LiveKit documentation through MCP.
2. Check current SDK APIs and examples.
3. Verify model availability and configuration.
4. Follow the recommended Python AgentSession architecture.
5. Avoid deprecated APIs.
6. Explain significant architectural decisions.

Use:
- AgentSession for voice orchestration.
- Agent for instructions and behaviour.
- LiveKit Inference for STT, LLM and TTS.
- Python function tools for business operations.

Prioritise:
- Low latency.
- Streaming responses.
- Turn detection.
- Interruption handling.
- Reliable tool execution.
- Error handling and recovery.

Preserve the working browser-to-agent integration.

Do not change working LiveKit session, token or dispatch behaviour without a demonstrated reason.

## 6. RAG, LlamaIndex and Qdrant Rules

### 6.1 LlamaIndex responsibilities

Use LlamaIndex for:
- Document ingestion.
- Text extraction.
- Chunking.
- Embedding integration.
- Index construction.
- Retriever abstractions.
- Metadata-aware retrieval.
- Semantic retrieval orchestration.

Keep LlamaIndex behind application-level service interfaces.

Do not put business rules or tenant authorization inside arbitrary LlamaIndex callbacks.

Do not introduce unnecessary LlamaIndex packages or integrations.

### 6.2 Qdrant responsibilities

Qdrant is the approved vector database.

Use it for:
- Dense vector search.
- Sparse or hybrid retrieval when justified.
- Semantic retrieval.
- Metadata filtering.
- Document and knowledge retrieval.
- Future tenant-aware retrieval.

Use the official LlamaIndex Qdrant integration where appropriate.

Keep Qdrant configuration outside application business logic.

Support:
- Local Qdrant using Docker.
- Future Qdrant Cloud deployment.

Use environment variables for the endpoint and API key.

Never expose Qdrant credentials to frontend code.

Never commit local Qdrant storage to Git.

### 6.3 Collection design

Start with a small number of logically separated collections.

Initial candidates:
- `dubai_market_knowledge`
- `dubai_property_knowledge`

Create a collection only when there is a genuine data source and retrieval use case for it.

Do not create one collection per customer.

Design future tenant isolation using a tenant identifier in Qdrant payload metadata and mandatory tenant filters.

Consider Qdrant tenant-aware payload indexes where appropriate.

Dedicated shards or separate collections may be considered later for customers with specific isolation or scaling requirements.

Do not implement complex sharding prematurely.

### 6.4 Payload metadata

Preserve relevant metadata with every indexed record.

Possible fields include:
- `tenant_id`
- `source`
- `dataset`
- `source_record_id`
- `record_type`
- `area`
- `property_type`
- `transaction_date`
- `ingested_at`
- `data_quality_status`

These are proposed fields, not assumptions about the Kaggle schema.

Only populate fields supported by actual source data.

Create Qdrant payload indexes for fields that are actually used in filters.

Create relevant indexes before bulk ingestion where practical.

### 6.5 Embedding configuration

Keep the embedding model configurable.

Document:
- Model name.
- Vector dimensions.
- Similarity metric.
- Chunking configuration.
- Embedding configuration version.

The ingestion and query pipelines must use compatible embedding configurations.

Do not silently change embedding models or vector dimensions for an existing collection.

Changing embedding dimensions or model configuration requires a controlled re-indexing strategy.

### 6.6 Hybrid retrieval

Use the right retrieval mechanism for each question.

Structured retrieval:
- Budget.
- Minimum and maximum price.
- Bedrooms.
- Property type.
- Area.
- Transaction date.
- Rental period.
- Numerical comparisons.
- Aggregations and averages.

Use DuckDB as the mandatory source for historical sales, rental and market
analytics. Future live property availability must come from a separate,
authoritative structured inventory source; historical records must never be
treated as current listings.

Semantic retrieval:
- Area descriptions.
- Community characteristics.
- Project descriptions.
- Amenities.
- Market research.
- Natural-language knowledge questions.

Use LlamaIndex to orchestrate semantic retrieval and Qdrant for semantic
vectors and metadata filtering. LlamaIndex and Qdrant are not sources of
truth for property availability, and LlamaIndex must not be used for exact
numerical calculations.

Combine structured and semantic retrieval when the question benefits from both.

Vector similarity alone must never be used to enforce exact numerical constraints.

Never rely on an LLM to calculate exact transaction statistics when a structured query can calculate them.

## 7. Real Estate Data Integrity

The initial real-estate data source is:

https://www.kaggle.com/code/sergionefedov/dubai-real-estate-full-eda-2020-2026/notebook

The first implementation uses only the `secondary_sales.csv` file from this
source. Other Kaggle CSV files and external data sources are deferred.

Investigate the underlying dataset before implementation.

Verify:
- Actual downloadable files.
- CSV schemas.
- Column names and types.
- Row counts.
- Date coverage.
- Missing values.
- Duplicate records.
- Dataset licence.
- Attribution requirements.
- Whether each record represents a transaction, rental contract, off-plan record or active listing.

Do not assume the Kaggle notebook licence automatically covers the underlying dataset.

Do not commit large raw datasets to Git.

Keep ingestion repeatable and document how to download and prepare the data.

### Strict factual rules

Historical transactions are not active property listings.

Historical rental contracts are not current rental availability.

Off-plan records must not automatically be represented as completed or available properties.

Never:
- Invent listing IDs.
- Invent property availability.
- Invent asking prices.
- Invent transaction dates.
- Present historical transaction prices as current asking prices.
- Present historical rental contracts as currently available rental units.

Always preserve source provenance and explain relevant dates and data limitations.

If an active inventory source is not available, clearly tell the customer that the system can provide historical market information but cannot confirm current availability.

## 8. Security Rules

- Never expose `LIVEKIT_API_SECRET` to browser code.
- Never expose server-side API keys through `NEXT_PUBLIC_` variables.
- Never commit `.env` files or credentials.
- Validate all API inputs.
- Keep authentication and token generation server-side.
- Use environment variables for configuration.
- Never print secrets in logs.
- Never expose Qdrant credentials to the browser.
- Never trust client-supplied tenant identifiers.
- Enforce tenant isolation in backend retrieval services.
- Do not allow one tenant to retrieve another tenant's documents.
- Do not execute arbitrary LLM-generated SQL.
- Validate and constrain tool arguments.
- Avoid logging sensitive customer information unnecessarily.

Authentication and rate limiting must be introduced before public production launch.

## 9. Coding Standards

### Python
- Type hints.
- Async/await where appropriate.
- Clear separation of services, tools, agent logic and configuration.
- Pydantic models for structured data where appropriate.
- Meaningful error handling.
- Automated tests.
- Reusable and testable business logic.

### TypeScript
- Strict typing.
- Reusable React components.
- Separate API, hooks, components and constants.
- Avoid unnecessary dependencies.
- Follow current Next.js App Router conventions.
- Consult installed Next.js documentation before making framework changes.

### General
- Small, focused files.
- Clear naming conventions.
- No unnecessary abstractions.
- No duplicated business logic.
- Maintain readable documentation.
- Keep dependencies minimal.
- Do not modify unrelated files.

## 10. Development Workflow

Work milestone by milestone.

### Before implementation

1. Inspect the existing project structure.
2. Check Git status and preserve unrelated changes.
3. Read relevant project instructions and installed skills.
4. Consult official documentation for technologies involved.
5. Identify relevant existing files.
6. Present the proposed implementation.
7. Identify dependencies, risks and expected outcomes.
8. Wait for approval when the task requests a read-only plan.

### During implementation

- Preserve existing working code.
- Make incremental changes.
- Avoid unnecessary dependencies.
- Run relevant tests and lint checks.
- Test integrations independently.
- Explain files created or modified.
- Report errors rather than hiding them.

### After implementation

- Summarise completed work.
- List files changed.
- Report tests and their actual results.
- Provide commands to run and test.
- Identify known limitations.
- Recommend a Git commit message.
- Do not claim success without verification.

Never modify unrelated files without a clear reason.

Do not commit or push unless explicitly requested.

## 11. Project Milestones

### Milestone 1 — Project foundation and Python LiveKit backend
Status: COMPLETED AND COMMITTED.

Includes:
- Monorepo foundation.
- Python LiveKit Agent.
- AgentSession configuration.
- STT, LLM and TTS through LiveKit Inference.
- Initial receptionist instructions.
- Backend configuration and tests.

### Milestone 2 — Next.js browser-to-agent integration
Status: COMPLETED AND COMMITTED.

Includes:
- Next.js call interface.
- Secure token endpoint.
- LiveKit session connection.
- Named agent dispatch.
- Microphone publishing.
- Agent audio playback.
- Transcript presentation.
- Call lifecycle and cleanup.

The browser-to-agent conversation has been verified end-to-end.

Preserve this working integration.

### Milestone 3 — Historical Sales Data Foundation

Current development milestone.

The initial scope is deliberately limited to one selected source file, subject
to verification: `secondary_sales.csv` from the Kaggle dataset above.

Initial implementation architecture:
- Python for ingestion and data processing.
- Pandas for CSV handling where appropriate.
- DuckDB for structured historical property queries and market analytics.
- The existing LiveKit agent for voice interaction and Python function tools.
- LlamaIndex and Qdrant remain approved future technologies for semantic
  retrieval, but are not introduced for numerical transaction records.

#### Phase 3A — Dataset verification
- Download and inspect the Kaggle source and selected CSV.
- Verify the actual file, schema, row count, date coverage, data quality,
  licence and attribution requirements.
- Confirm that the selected records represent historical secondary sales and
  are not active property listings.
- Present a read-only implementation plan and wait for approval.

#### Phase 3B — Cleaning and DuckDB ingestion
- Use Python and Pandas for CSV handling where appropriate.
- Validate and clean the selected data.
- Preserve source identifiers, dates and provenance.
- Load the cleaned records into DuckDB.
- Generate data-quality reports.

#### Phase 3C — Historical sales queries
- Implement structured historical sales queries in DuckDB.
- Implement area-level market insights and numerical aggregations.
- Keep exact filters and calculations in DuckDB rather than in vector search
  or the LLM.

#### Phase 3D — Existing LiveKit agent integration
- Expose approved historical sales and area-insight queries through Python
  function tools on the existing LiveKit agent.
- Preserve the working browser-to-agent voice integration.
- Test complete voice interactions against the historical sales data.

The following remain approved for future semantic retrieval but are explicitly
deferred from this initial implementation:
- Other Kaggle CSV files.
- Dubai Land Department integration.
- Additional external datasets.
- Qdrant deployment.
- LlamaIndex indexing.
- Embedding generation.
- Advanced hybrid search.
- PostgreSQL, authentication, CRM and billing.

Do not introduce LlamaIndex or Qdrant merely to process numerical transaction
records. Do not treat this scope as permission to implement deferred systems.

### Milestone 4: AI Property Sales Agent

Transform the existing VoiceForce AI receptionist into an interactive Dubai property sales consultant for the Prime Properties demo.

**Core capabilities**

1. **Buy vs Rent Intent**
   - Understand whether the customer wants to buy or rent.
   - Ask clarifying questions when intent is unclear.

2. **Customer Preference Collection**
   - Preferred Dubai community or location.
   - Property type: apartment, villa, townhouse, penthouse or studio.
   - Number of bedrooms and bathrooms.
   - Furnishing preferences.
   - Ready or off-plan preference.

3. **Budget Qualification**
   - Understand the customer's budget in AED.
   - Distinguish purchase budgets from annual rental budgets.
   - Ask follow-up questions when budget information is incomplete.

4. **Property Search**
   - Search the existing DuckDB `demo_property_listings` table.
   - Filter by transaction type, location, property type, bedrooms and budget.
   - Return matching properties with their IDs, prices and details.
   - Recommend the most relevant matching properties.
   - Clearly identify all demo inventory as synthetic and simulated.
   - Never claim simulated availability is verified or real.

5. **Lead Capture**
   - Collect customer name and contact number when appropriate.
   - Capture buying/renting intent, budget and property preferences.
   - Ask for customer consent before saving contact information.
   - Store demo leads in a separate DuckDB table.
   - Do not introduce CRM integrations in this milestone.

6. **Structured Customer Information**
   - Maintain customer preferences throughout the conversation.
   - Avoid repeatedly asking questions already answered.
   - Return a structured customer enquiry/lead object.
   - Confirm important customer details before saving.

**Technical constraints**

- Use the existing Python LiveKit Agent and function tools.
- Use DuckDB for property search and demo lead storage.
- Preserve the existing `secondary_sales` historical dataset.
- Keep `demo_property_listings` separate from historical sales.
- Keep the existing LiveKit STT, LLM, TTS and Next.js integration unchanged.
- Do not introduce Qdrant, LlamaIndex, PostgreSQL, authentication or CRM integrations yet.
- Do not invent property records or availability.
- Make the distinction between simulated demo inventory and verified live inventory explicit.

**Expected outcome**

A customer can have a natural voice conversation with the Prime Properties AI sales consultant, describe their requirements, receive matching demo property recommendations, and submit a structured enquiry with their consent.

### Milestone 5 — Appointment and viewing workflow
- Customer availability collection.
- Viewing request creation.
- Scheduling integrations.
- Confirmation and error handling.

### Milestone 6 — VoiceForce AI dashboard
- Call history.
- Conversation transcripts.
- Call summaries.
- Lead management.
- Agent performance information.

### Milestone 7 — Authentication and multi-tenancy
- User authentication.
- Organization and tenant models.
- Authorization.
- Tenant data isolation.
- Secure API access.

### Milestone 8 — PostgreSQL and persistent application data
- Application database.
- Customer records.
- Leads.
- Calls and summaries.
- Appointment records.
- Database migrations.

### Milestone 9 — CRM and external integrations
- CRM connectors.
- Calendar integrations.
- Communication services.
- MCP integrations where appropriate.

### Milestone 10 — Monitoring and observability
- Voice session tracing.
- STT, LLM and TTS latency.
- Tool execution metrics.
- Error tracking.
- Usage and cost monitoring.

### Milestone 11 — Deployment and production readiness
- Production deployment.
- Qdrant Cloud or production vector infrastructure.
- Security review.
- Rate limiting.
- Scalability.
- Reliability and recovery.
- Billing and SaaS readiness.

Do not jump ahead or implement future milestones prematurely.

## 12. Current Development Objective

Our current objective is Milestone 3: Historical Sales Data Foundation.

The first task is read-only verification of the Kaggle dataset and the
`secondary_sales.csv` file selected for the initial implementation.

Before writing code:
1. Inspect the actual repository and Git status.
2. Inspect the Kaggle notebook and verify the actual downloadable
   `secondary_sales.csv` file.
3. Verify the dataset licence and attribution requirements.
4. Identify the selected file's schema, data quality issues and useful sales
   and area fields.
5. Determine the DuckDB table and historical sales query strategy.
6. Propose the area-level market insight queries.
7. Propose the Python function-tool interface for the existing LiveKit agent.
8. Identify only the dependencies and testing requirements needed for this
   initial scope.
9. Present the implementation plan and wait for approval.

Do not modify files during the initial investigation.

### Expected first deliverable

A clear, evidence-based implementation plan containing:
- The verified Kaggle source and selected `secondary_sales.csv` file.
- The actual schema, data-quality findings and date coverage.
- Dataset licence and attribution.
- Proposed Python/Pandas ingestion and cleaning pipeline.
- DuckDB schema, historical sales query strategy and area insights.
- Proposed LiveKit Python function-tool interface.
- Minimal dependencies for the initial implementation.
- Files to create or modify.
- Testing strategy.

Preserve the completed Milestone 1 and Milestone 2 functionality.

Do not implement other data sources, Dubai Land Department integration,
Qdrant, LlamaIndex indexing, embeddings, advanced hybrid search, CRM,
PostgreSQL, authentication, billing, live property feeds or complex
dashboards during the initial Milestone 3 implementation.

Prioritise reliable data, accurate retrieval, source transparency and a working voice-agent experience.

---


## 13. VoiceForce AI — Voice Performance and Latency Optimisation

### 13.1 Immediate Engineering Objective

Our immediate engineering priority is to minimise voice-agent response latency while improving speech detection accuracy and natural conversational turn-taking.

The objective is to make VoiceForce AI feel like a real-time human conversation.

This is a parallel performance optimisation workstream. It does not automatically replace or cancel the existing project milestones.

### 13.2 Existing Approved Voice Stack

Verify actual implementation before making assumptions.

- Audio transport: LiveKit Cloud / WebRTC.
- Agent runtime: Python LiveKit Agents.
- Session orchestration: AgentSession.
- STT: AssemblyAI Universal-3-6-Pro through LiveKit Inference.
- LLM: OpenAI GPT-5 Mini through LiveKit Inference.
- TTS: Fish Audio S2.1 Pro through LiveKit Inference.
- Turn detection: LiveKit turn detection.

Do not replace these components without measured evidence and an approved technical proposal.

### 13.3 Performance Objectives

Prioritise:

1. Reduce end-of-turn-to-first-audio latency.
2. Improve VAD speech-start detection.
3. Improve end-of-speech detection.
4. Reduce unnecessary silence waiting.
5. Optimise STT streaming and endpointing.
6. Reduce LLM time-to-first-token.
7. Reduce TTS time-to-first-audio.
8. Optimise audio buffering and playback.
9. Improve barge-in and interruption handling.
10. Maintain reliable performance in noisy environments.

### 13.4 Required Performance Metrics

Instrument and measure:

- End-of-turn-to-first-audio latency.
- P50, P90 and P95 latency.
- VAD speech-start detection delay.
- End-of-speech detection delay.
- STT transcription delay.
- LLM time-to-first-token (TTFT).
- TTS time-to-first-audio (TTFA).
- Audio playback startup delay.
- False endpoint rate.
- Missed speech rate.
- Transcription accuracy.
- Barge-in success rate.

Use existing LiveKit observability and metrics wherever possible.

Do not invent measurements or report targets as achieved results.

### 13.5 Speech Detection and Turn-Taking

Investigate:

- LiveKit VAD configuration.
- AssemblyAI endpointing and interim transcription.
- Speech probability thresholds.
- Audio frame duration.
- Silence timeout.
- Adaptive end-of-turn detection.
- Acoustic echo and background noise.
- False speech detection.
- Premature interruption.
- User interruption while the agent is speaking.

Distinguish speech detection from conversational turn completion.

Do not reduce silence thresholds blindly. Preserve natural conversational pauses and avoid cutting users off.

### 13.6 Streaming and Latency Optimisation

Investigate:

- Streaming STT.
- Streaming LLM generation.
- Preemptive LLM generation where appropriate.
- Streaming TTS.
- Sentence-level or phrase-level audio generation.
- Asynchronous processing.
- Unnecessary sequential operations.
- Audio buffering and playback.
- WebRTC transport overhead.
- Tool execution latency.

The agent should begin generating and playing audio as early as safely possible without waiting unnecessarily for the complete response.

### 13.7 Evaluation Scenarios

Test:

- Normal conversational speech.
- Fast speech.
- Slow speech with natural pauses.
- Short acknowledgements.
- Background noise.
- Laptop microphone and speakers.
- Acoustic echo.
- User interruption.
- English and Urdu speech.

The existing noisy-room laptop microphone and speaker test should be retained as an evaluation scenario.

### 13.8 Engineering Workflow

Before optimisation:

1. Inspect the existing implementation.
2. Review Git status and preserve unrelated changes.
3. Consult installed LiveKit Agent Skills and official documentation.
4. Trace the complete audio pipeline.
5. Instrument existing components.
6. Establish baseline measurements.
7. Identify the largest bottleneck.
8. Present a prioritised optimisation proposal.

After approval:

1. Implement one optimisation at a time.
2. Run relevant automated tests.
3. Repeat the same benchmark scenarios.
4. Compare before-and-after metrics.
5. Document regressions and trade-offs.
6. Preserve working browser-to-agent integration.

Do not rewrite the voice architecture without evidence.

### 13.9 Definition of Done

An optimisation is complete only when:

- The bottleneck has been identified.
- The technical change is documented.
- Tests have been executed.
- Before-and-after measurements are available.
- Latency improvement is demonstrated.
- Speech detection quality has not regressed.
- Existing voice interactions continue working.

### 13.10 Immediate First Task

Conduct a READ-ONLY technical audit of the existing VoiceForce AI voice pipeline.

Deliver:

1. Actual voice architecture and component configuration.
2. Complete audio processing flow.
3. Existing latency instrumentation.
4. Identified performance bottlenecks.
5. Baseline benchmark plan.
6. Prioritised optimisation recommendations.
7. Files that would need modification.
8. Testing and evaluation strategy.

Do not modify application code during this initial audit.

Wait for explicit approval before implementation.


# 14. VoiceForce AI — Multilingual Speech Module (English, Arabic & Urdu)

## 14.1 Objective

Extend the existing VoiceForce AI voice agent to support natural, real-time conversations in:

- English (`en`)
- Arabic (`ar`)
- Urdu (`ur`)

The initial target markets are UAE and Pakistan.

The agent must understand and respond in the customer's preferred language, with natural pronunciation, minimal response latency and reliable conversational turn-taking.

This is a parallel capability workstream. It must preserve the existing English implementation and must not automatically replace or cancel the existing project milestones.

## 14.2 Approved Architecture

Preserve the existing architecture:

- LiveKit Cloud / WebRTC for audio transport.
- Python LiveKit Agents for agent execution.
- AgentSession for conversation orchestration.
- LiveKit Inference for speech and language models.
- OpenAI GPT-5 Mini for LLM inference initially.
- Existing Python function tools and business logic.
- Existing Next.js frontend.

Keep speech providers configurable and isolated behind application-level configuration.

Do not introduce local speech models, separate Whisper infrastructure, RealtimeTTS servers or unnecessary microservices.

## 14.3 Speech-to-Text (STT)

Primary candidate:

AssemblyAI Universal-3.6 Pro through LiveKit Inference.

Model:
`assemblyai/universal-3-6-pro`

Required languages:
- English
- Arabic
- Urdu

Requirements:

- Streaming speech recognition.
- Automatic language detection.
- Language confidence metadata.
- English, Arabic and Urdu code-switching.
- Support for natural Pakistani Urdu.
- Arabic recognition suitable for UAE customers.
- Accurate recognition of property terminology, locations, names and prices.
- Interim transcription where supported.
- Low-latency endpointing.

Investigate:

- `language_detection`
- `language_codes`
- `mode="min_latency"`
- `keyterms_prompt`
- Streaming partial transcripts.
- `min_turn_silence` and `max_turn_silence`.
- STT endpointing and VAD interaction.

Benchmark minimum-latency and balanced configurations. Do not sacrifice transcription accuracy or natural conversational pauses simply to reduce latency.

Do not assume Roman Urdu and Urdu-script transcription perform equally well. Evaluate both separately.

## 14.4 Text-to-Speech (TTS)

Primary candidates:

1. Inworld Realtime TTS 2 Flash:
   `inworld/inworld-tts-2-flash`

2. Inworld Realtime TTS 2:
   `inworld/inworld-tts-2`

Both are candidates for Arabic and Urdu speech generation through LiveKit Inference.

Evaluate:

- Time to first audio (TTFA).
- Streaming audio generation.
- P50, P90 and P95 latency.
- Arabic pronunciation and fluency.
- Pakistani Urdu pronunciation and fluency.
- Voice naturalness.
- Voice consistency.
- Numbers, dates, currencies and property terminology.
- Audio stability during long responses.

Keep Fish Audio S2.1 Pro as the existing English baseline until benchmark results justify a change.

Do not assume Fish Audio S2.1 Pro supports Urdu.

Do not select a TTS provider solely on advertised speed or language coverage. Verify actual voice availability, quality and streaming behaviour.

Maintain configurable voice IDs for each supported language.

## 14.5 Multilingual Language Router

Implement a lightweight language-routing component.

Responsibilities:

- Identify the customer's spoken language using STT language metadata.
- Support English, Arabic and Urdu.
- Preserve the customer's preferred language throughout the conversation.
- Handle natural language switching.
- Support English-Urdu and English-Arabic mixed speech.
- Route the response to the appropriate TTS voice.
- Avoid unnecessary language-detection LLM calls.

Language detection must not introduce an additional sequential network request.

Use confidence thresholds and conversation context to prevent unnecessary language switching.

If detection confidence is low, retain the existing conversation language or ask a short clarification when necessary.

Do not automatically translate the customer's message into English unless the business operation requires it.

## 14.6 LLM Response Behaviour

The LLM must:

- Respond in the customer's preferred language.
- Understand English, Arabic and Pakistani Urdu.
- Handle mixed-language conversations naturally.
- Preserve names, addresses, numbers and property terminology.
- Avoid unnecessary English translations.
- Use concise, conversational sentences suitable for spoken delivery.
- Maintain the same business rules and tool permissions across all languages.

Arabic responses must use natural conversational Arabic appropriate for UAE customers. Evaluate Modern Standard Arabic and Gulf conversational Arabic.

Urdu responses must use natural Pakistani Urdu rather than Hindi-style vocabulary.

Maintain one consistent agent identity and business personality across languages.

## 14.7 Low-Latency Requirements

Prioritise:

- Streaming STT.
- Early language identification.
- Streaming LLM generation.
- Streaming TTS.
- Sentence-level or phrase-level audio generation.
- Minimal additional processing between pipeline stages.
- Early audio playback.
- Reliable interruption handling.
- Efficient audio buffering.
- Avoiding unnecessary sequential model calls.

The language router must operate locally within the agent process wherever possible.

Do not wait for the complete LLM response before beginning TTS when the provider and LiveKit integration support safe streaming.

Do not change the existing VAD and endpointing configuration without controlled benchmark comparisons.

## 14.8 Performance Instrumentation

Extend existing latency instrumentation with language-specific dimensions.

Capture:

- `language_code`
- `language_confidence`
- `stt_ttft`
- `stt_final_transcript_delay`
- `language_detection_delay`
- `llm_ttft`
- `llm_generation_duration`
- `tts_ttfa`
- `tts_generation_duration`
- `end_of_turn_to_first_audio`
- `e2e_latency`
- `barge_in_success`
- `transcription_accuracy`

All latency metrics must be segmented by language and provider configuration.

Do not log raw customer speech, transcripts or personally identifiable information unnecessarily.

Use the existing anonymized telemetry infrastructure.

Report P50, P90 and P95 with sample counts.

## 14.9 Evaluation Scenarios

Test each language independently and in mixed-language conversations.

English:
- Existing receptionist conversations.
- Property enquiries.
- Buy and rent qualification.

Arabic:
- UAE conversational Arabic.
- Modern Standard Arabic.
- Property enquiries.
- Arabic numbers, locations and prices.

Urdu:
- Pakistani conversational Urdu.
- Urdu script.
- Roman Urdu.
- Property enquiries.
- Pakistani accents and natural speaking speed.

Mixed-language scenarios:
- English and Urdu.
- English and Arabic.
- Urdu and English property terminology.
- Arabic and English property terminology.
- Switching language during an active conversation.

Audio conditions:
- Normal speech.
- Fast speech.
- Slow speech and natural pauses.
- Background noise.
- Laptop microphone and speakers.
- Acoustic echo.
- User interruptions.
- Short acknowledgements.

## 14.10 Benchmark and Definition of Done

Run the same benchmark methodology against the existing English baseline.

For each language and provider combination, report:

- STT accuracy.
- Language detection accuracy.
- LLM TTFT.
- TTS TTFA.
- End-of-turn-to-first-audio latency.
- End-to-end P50, P90 and P95.
- Interruption success rate.
- Provider cost per minute.

Suggested initial engineering targets, not achieved results:

- STT finalization: P50 under 500 ms after actual end of speech.
- TTS first audio: P50 under 500 ms after the first eligible text chunk.
- End-of-turn-to-first-audio: P50 under 1.5 seconds.
- End-to-end latency: P50 under 2 seconds where the interaction and measurement definition permit.
- No significant regression in English performance.
- No material regression in speech recognition accuracy.

Measure these targets using clearly defined timestamps and sufficient sample sizes. Separate endpointing delay from provider processing latency.

## 14.11 Implementation Workflow

Before implementation:

1. Inspect the actual repository and Git status.
2. Inspect the existing STT, LLM, TTS and AgentSession implementation.
3. Read the installed LiveKit Agent Skills and official documentation.
4. Verify current model availability and language support.
5. Verify dynamic language and TTS voice switching APIs.
6. Verify provider voice availability and regional support.
7. Establish the existing English benchmark.
8. Prepare a read-only technical implementation proposal.

After approval:

1. Implement multilingual STT configuration.
2. Implement language detection and routing.
3. Integrate and benchmark multilingual TTS.
4. Implement multilingual response instructions.
5. Add language-specific telemetry.
6. Run automated and real-world voice evaluations.
7. Compare before-and-after performance.
8. Document provider costs, latency and limitations.

Implement incrementally. Preserve the existing working English browser-to-agent integration.

Do not introduce unnecessary dependencies or rewrite unrelated application components.

## 14.12 Immediate First Task

Conduct a READ-ONLY audit and research task.

Deliver:

- Verified Arabic and Urdu STT options.
- Verified Arabic and Urdu TTS options.
- Recommended provider combinations.
- Current LiveKit integration compatibility.
- Dynamic language-switching architecture.
- Voice availability and pronunciation considerations.
- Provider latency and pricing comparison.
- Proposed language-router implementation.
- Required files and configuration changes.
- Multilingual benchmark and testing plan.
- Risks, limitations and fallback strategy.

Do not modify application code during this initial investigation.

Wait for explicit approval before implementation.

The ultimate objective is a production-quality multilingual VoiceForce AI receptionist that can naturally communicate with customers in English, Arabic and Pakistani Urdu without compromising the existing English experience or voice-response latency.


<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

<!-- BEGIN:nextjs-agent-feedback -->

## Report Next.js feedback

The project owner enabled `experimental.agentFeedback`, authorizing this feedback pass. When enabled, `next dev` writes this block and restores it if removed. Commit `AGENTS.md` with your work to keep the tree clean.

During the current user request, retain anonymized facts as feedback candidates for meaningful or recurring Next.js issues:

- Crashes, hangs, OOMs, or unexpected slowness
- Incorrect behavior, output, errors, or diagnostics
- Missing, unclear, or conflicting documentation
- Unexpected CLI, codemod, Skill, or upgrade behavior and non-obvious workarounds

Continue the current user request without reporting immediately. Routine debugging is not feedback. Verify changes before retaining them as feedback candidates. Never retain code, logs, paths, URLs, secrets, personal information, or project-specific data.

Retain qualifying friction even if it is later fixed or worked around; record the final outcome during the reporting pass.

Before the final response, run one reporting pass. If candidates remain, from this file's directory run `npx --no-install next internal agent-feedback-instructions` once without piping or truncating its output. Follow its output or error guidance. If a network sandbox blocks it, retry with network access; if it still returns no output, continue normally.

<!-- END:nextjs-agent-feedback -->

# 15. Active Work Order — English Voice Pipeline Latency Optimization

This section is the active implementation brief and supersedes conflicting initial-provider choices in earlier sections for this milestone only. The task is to inspect and modify the existing application, not to produce a read-only proposal.

## 15.1 Objective and scope

Reduce the time from caller end-of-turn to the first useful spoken sentence. The two primary optimization metrics are:

- `llm_node_ttft`: time to first LLM token.
- `llm_node_ttfs`: time to first sentence from the LLM.

The latest isolated browser run supplied by the owner is a diagnostic baseline (small sample; not a production percentile):

| Metric | P50 | P95 |
| --- | ---: | ---: |
| End-to-end latency | 3.605 s | 5.594 s |
| End-of-turn delay | 0.647 s | 1.111 s |
| Transcription delay | 0.635 s | 1.090 s |
| LLM TTFT | 2.018 s | 3.988 s |
| LLM TTFS | 2.711 s | 4.176 s |
| TTS TTFB | 0.311 s | 0.334 s |
| Tool duration | 0.231 s | 0.380 s |

Treat these as owner-provided observations from a mixed-language run, not a clean English-only benchmark. Establish a fresh English-only baseline before claiming improvements. Do not add overlapping stage durations to calculate E2E.

The current intended English stack for this workstream is:

- STT: AssemblyAI Universal-3.6 Pro through LiveKit Inference; keep unchanged.
- LLM: replace the hard-coded GPT-5 Mini default with a configurable, benchmark-selected low-latency LiveKit Inference model.
- TTS during this optimization: Fish Audio S2.1 Pro through LiveKit Inference (`fishaudio/s2.1-pro`), after verifying current SDK/model/voice support.
- Runtime: Python LiveKit Agents, AgentSession, AgentServer, existing LiveKit Cloud/WebRTC and Next.js browser integration.

The owner reports an Inworld TTS-2 Flash concurrency limitation of five concurrent connections, after which synthesis may stop. Therefore do not use Inworld TTS-2 Flash as the default production/test TTS for concurrency tests above five simultaneous connections. Use Fish Audio S2.1 Pro for the current English path. Once the LLM bottleneck is demonstrably improved, run a separate controlled TTS evaluation of Inworld TTS-2 and Inworld TTS-2 Flash, respecting provider limits and verifying current availability. Do not conflate TTS work with the primary LLM optimization.

This is an English-first latency milestone. Preserve the existing Urdu/Arabic language-router code and voice configuration unless a change is strictly required for correctness. Do not spend time benchmarking Urdu or Arabic in this milestone, do not claim those routes were validated, and do not silently route them to an English voice. Document any remaining Inworld concurrency exposure on those frozen routes.

## 15.2 Mandatory repository audit before edits

Inspect the actual working tree, not just this instruction file:

- Run `git status --short` and preserve all user changes.
- Read the root `AGENTS.md`, backend package/dependency files and lockfile.
- Inspect `backend/src/voiceforce_agent/config.py`, `server.py`, `receptionist.py`, `language_router.py`, `latency_metrics.py`, welcome/agent handoff code, tool/database services, tests, and benchmark scripts.
- Inspect the current frontend/browser latency instrumentation and `docs/latency-baseline.md`.
- Trace the actual path from final user transcript -> LLM stream -> sentence segmentation -> TTS stream -> LiveKit audio frames.
- Identify any full-response buffering, blocking calls on the event loop, unnecessary sequential calls, repeated prompt/context construction, excessive tool schemas, or extra model round trips.
- Do not assume an earlier implementation description is still accurate.

Known observations from the repository review at the time this section was written (verify against the current checkout):
- `config.py` hard-codes `openai/gpt-5-mini` with `reasoning_effort=low`.
- `server.py` constructs one `AgentSession`, uses AssemblyAI, attaches the latency listeners, and enables preemptive generation with `{"enabled": True}`.
- `receptionist.py` already overrides `tts_node` as an async generator and forwards audio frames with `async for` / `yield`.
- Its synchronous DuckDB/storage operations are already moved off the event loop using `asyncio.to_thread` in tool wrappers. Audit all paths before changing them; do not replace working thread offloads with blocking calls.
- The default LiveKit LLM node is not overridden in the inspected implementation. Prefer the framework's native streaming node unless a measured, justified customization is needed.
- Existing latency instrumentation records LLM TTFT, TTFS, tokens/sec, TTS TTFB and E2E metrics. Extend it only where a real missing timestamp prevents diagnosis; do not duplicate or redefine existing metrics.

## 15.3 LiveKit Docs MCP and Agent Skills are mandatory

Use Codex's LiveKit Docs MCP server and installed LiveKit Agent Skills before and during implementation. Do not rely on model memory for a fast-changing SDK.

1. Check the configured MCP server and confirm it can search and fetch current LiveKit documentation. If absent, tell the owner and install/configure it using the official Codex command:
   `codex mcp add --url https://docs.livekit.io/mcp livekit-docs`
2. Check the installed LiveKit Agent Skill. If absent, install the official skill using:
   `npx skills add livekit/agent-skills --skill livekit-agents`
3. If using the LiveKit CLI skill workflow, inspect `lk --version`, then use `lk skills install` / `lk skills update` as appropriate. Do not overwrite local skill customizations without reviewing the diff.
4. Use the MCP to search and fetch the complete current documentation for: AgentSession, Agent/Agent.default.llm_node, streaming LLM and TTS nodes, LiveKit Inference LLM model catalogue and parameters, Fish Audio S2.1 Pro, Inworld TTS-2, turn handling, preemptive generation, async function tools, cancellation, observability and testing.
5. Read the installed skill's relevant guidance for building, debugging, operating and testing agents. Follow its workflow and use the LiveKit agent debugger/simulations when supported.
6. Record the exact documentation pages/API signatures and SDK version used in the implementation summary.

Official references to start with (fetch current pages through MCP rather than treating these links as frozen API contracts):
- https://docs.livekit.io/mcp
- https://docs.livekit.io/agents/logic/sessions/
- https://docs.livekit.io/agents/logic/turns/tuning/
- https://docs.livekit.io/agents/models/llm/
- https://docs.livekit.io/agents/models/tts/fishaudio/
- https://docs.livekit.io/reference/python/livekit/agents/

## 15.4 LLM model upgrade and configuration

Do not blindly select a model because it is newer, larger, or advertised as fast. Use LiveKit's current Inference catalogue via MCP and verify each model is available to this LiveKit project, supports streaming, and supports the required function/tool calling.

At minimum, evaluate:
- Existing baseline: `openai/gpt-5-mini`.
- LiveKit's currently documented recommended voice-agent model: `google/gemma-4-31b-it`.
- One or more currently available low-latency alternatives from the official catalogue, selected from current documentation (for example a current Flash model or GPT-5.4 Mini if still listed and available).

The examples above are candidates, not an instruction to assume availability or performance. Verify model IDs, retirement/deprecation status, model parameters and tool-call support using the MCP documentation and actual LiveKit Inference response. Do not invent model IDs or pass unsupported reasoning parameters.

Implementation requirements:
- Make the selected LLM model configurable through a server-only environment variable such as `VOICEFORCE_LLM_MODEL`.
- Keep a documented safe fallback/rollback to the current GPT-5 Mini model.
- Keep model-specific parameters in a small explicit configuration layer. Apply reasoning/verbosity controls only when the selected model documents and accepts them.
- Avoid initializing multiple production LLMs per call. Benchmark candidates in isolated runs/configurations.
- Keep tool schemas and agent instructions concise, but preserve every business rule, safety rule, tool permission and grounding constraint.
- Inspect actual prompt token counts and conversation-history growth. Do not truncate required context or silently remove relevant history.
- Ensure tool calls remain supported and correctly handled. Measure tool-call selection and argument accuracy, not latency alone.
- Do not add a second LLM call for language detection, classification, rewriting or response polishing unless the task proves it is necessary.
- Do not move to Ollama/Llama 3.2 in this milestone unless the owner explicitly changes scope. This workstream is focused on LiveKit Inference model selection and orchestration.

Choose the default model only after a controlled benchmark. Report the winning model and why; leave the previous model available for rollback.

## 15.5 Async programming, streaming, yield and cancellation

Use LiveKit's native async streaming APIs and generator contract.

- Preserve the async generator pipeline. Consume streams with `async for` and forward chunks/frames with `yield` as soon as safely available.
- Do not call `collect()`, accumulate the complete LLM response, or wait for the full answer before passing eligible text to the TTS node in the live voice-response path.
- Do not add a custom `llm_node` override merely for style. The default LiveKit LLM node already streams chunks. If an override is necessary for instrumentation or a required transformation, delegate to the documented default implementation and forward each chunk immediately using `async for` and `yield`; preserve tool-call chunks, usage metadata, flush sentinels and cancellation semantics.
- Keep sentence/phrase segmentation streaming-aware. Do not add arbitrary large buffers or wait for a paragraph. Measure the gap between first token, first complete sentence (TTFS), first text forwarded to TTS, TTS first audio byte and first published audio frame wherever the installed SDK exposes reliable events.
- Preserve the existing async `tts_node` frame-forwarding behavior. Verify whether the selected Fish Audio Inference TTS exposes native streaming capability. Let LiveKit's supported adapter/tokenizer handle non-streaming providers rather than building a second buffering layer.
- Do not call synchronous network clients, file operations, DuckDB queries, Pandas operations or other blocking I/O directly on the event loop. Reuse the existing `asyncio.to_thread` wrappers for synchronous database operations; use native async clients for async-capable network I/O.
- Use `asyncio.gather` or TaskGroup only for independent operations whose results are all required. Do not parallelize dependent operations, duplicate database work, or create speculative tools that add load.
- Add explicit timeouts and meaningful error handling to external I/O. Ensure cancellation propagates when a caller interrupts, the turn is superseded, or the session ends. Do not swallow `CancelledError` or leave orphan tasks.
- Do not assume `asyncio.to_thread` stops the underlying synchronous operation on cancellation. Keep operations bounded and safe.
- Do not create untracked background tasks for work required to answer the current turn.
- Do not add unnecessary locks or serialize independent sessions globally.

## 15.6 LiveKit turn handling and preemptive generation

Audit the installed SDK's exact API before changing options.

- Preserve preemptive LLM generation if current behavior and tests confirm it is enabled and working.
- Verify whether preemptive TTS is supported by the installed SDK/provider combination. Test it as a separate condition; it can waste TTS work when the caller continues speaking.
- Do not assume a setting is enabled merely because it is enabled by default in the latest docs. Inspect the installed version and effective session configuration.
- Do not aggressively reduce endpointing delays to mask slow LLM TTFT. Tune EOU separately with short acknowledgements, natural pauses, long utterances, noisy audio and interruption tests.
- Preserve barge-in: cancel obsolete LLM/TTS generation and stop stale audio promptly. Prevent duplicate or late responses after a caller correction.
- Do not change STT model/configuration in this milestone except for a separately justified bug fix. Keep AssemblyAI Universal-3.6 Pro as the baseline.

## 15.7 TTS provider and concurrency policy

For the English optimization path:
- Configure LiveKit Inference Fish Audio S2.1 Pro using the verified model ID `fishaudio/s2.1-pro`.
- Verify the current voice parameter, streaming capability, supported English locale and model options via MCP.
- Use an environment variable for the Fish Audio voice ID. Do not invent a voice ID or silently reuse an Inworld voice ID. If no valid Fish Audio voice is configured, fail clearly with setup instructions or use only a documented provider default if the current LiveKit docs explicitly support one.
- Keep Fish Audio parameters conservative initially; do not add expressive markup, transforms or speed changes until a baseline is captured.
- Do not use Inworld TTS-2 Flash for concurrency tests exceeding the owner-reported five-connection limit.
- After LLM TTFT/TTFS has been optimized and a fresh baseline is captured, benchmark `inworld/inworld-tts-2` and `inworld/inworld-tts-2-flash` separately against Fish Audio, within documented quotas. Compare TTFB, first audible audio, naturalness, intelligibility, pronunciation and stability.
- Do not change Urdu/Arabic provider routing or claim multilingual support has been revalidated in this English milestone.

## 15.8 Prompt, tools and context optimization

- Measure actual prompt token counts for the same scenarios before and after each change.
- Remove duplicated instructions, irrelevant tool schemas and repeated static context only when semantics are preserved.
- Keep concise spoken-response rules (one or two natural sentences when appropriate) without sacrificing necessary clarifications or factual grounding.
- Keep historical sales, synthetic demo inventory and lead-consent constraints intact.
- Do not include irrelevant database schema or full result sets in every prompt. Retrieve only relevant data through the existing approved tools.
- Do not bypass Qdrant/DuckDB architecture rules, invent live property availability, or allow arbitrary LLM-generated SQL.
- Preserve privacy: no raw transcript text or PII in latency logs.

## 15.9 Tests and benchmark acceptance

Before changes, save a fresh English-only baseline with the existing code. Keep the same audio, prompts, tools, browser, region, warm/cold state and concurrency for every comparison.

Use the existing telemetry and scripts. Report sample count and P50/P90/P95/max for:
- LLM TTFT, TTFS and tokens/second.
- TTS TTFB.
- EOU and transcription delay.
- End-to-end latency from the existing authoritative metric.
- Tool duration and database duration.
- Prompt tokens, selected model, TTS model and provider request IDs where safely available.

Minimum initial comparison: 30 measured English turns per model/configuration; target 100+ turns before making a production P95 claim. Separate greeting/cold start from steady-state turns. Do not mix Urdu/Arabic samples into the English benchmark. Do not infer percentiles from fewer observations than were collected.

Run:
- Unit tests for configuration, model selection, tool wrappers and TTS routing.
- Static checks/formatting used by the repository.
- LiveKit agent debugger or existing scenario runner.
- Browser end-to-end voice tests with real audio.
- Tool-call scenarios, multi-turn context, short acknowledgements, long pauses, caller interruption, cancellation, and noisy microphone conditions.
- A concurrency test for the selected TTS provider within its documented/owner-supplied limits.

Acceptance:
- Demonstrated improvement in English LLM TTFT and TTFS versus the fresh GPT-5 Mini baseline.
- No regression in tool-call correctness, factual grounding, customer consent or property-data integrity.
- No full-response buffering in the critical response path.
- No blocking I/O on the event loop in the audited hot path.
- No duplicate/stale speech after interruption.
- Existing browser-to-agent integration continues to work.
- TTS provider and concurrency limitations are explicit.
- All results include sample counts and test conditions; no unmeasured performance claims.

Suggested goals (targets only, not promises): LLM TTFT P50 < 500 ms, TTFS P50 < 700 ms, and end-of-turn-to-first-audio P50 < 1.5 s. Report actual results even if these targets are not reached.

## 15.10 Implementation workflow and deliverables

Implement this workstream directly after completing the audit; do not stop after writing a proposal unless a required credential, voice ID, MCP installation or destructive decision blocks progress.

1. Report a concise audit of the current hot path and Git status.
2. Capture the fresh English baseline.
3. Implement configurable LLM model selection and benchmark candidates.
4. Select the best measured model; retain rollback configuration.
5. Verify/implement native async streaming and yield behavior end to end.
6. Audit tool concurrency, blocking I/O and cancellation; change only proven problems.
7. Configure Fish Audio S2.1 Pro for English, respecting the voice-ID requirement.
8. Test LiveKit preemptive generation and preemptive TTS as isolated variants.
9. Run unit, debugger and browser tests.
10. Update `docs/latency-baseline.md` with the exact model/provider configuration, benchmark method, results, sample counts, limitations and rollback instructions.
11. Summarize changed files, dependency/API upgrades, MCP docs and skills used, test commands/results, measured before/after latency, remaining bottlenecks and a suggested commit message.

Do not commit or push unless explicitly requested. Do not modify frontend, token generation, dispatch, database schema or unrelated milestones unless a demonstrated dependency requires it.
