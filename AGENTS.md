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

Use DuckDB or an authoritative structured inventory source for these queries.

Semantic retrieval:
- Area descriptions.
- Community characteristics.
- Project descriptions.
- Amenities.
- Market research.
- Natural-language knowledge questions.

Use LlamaIndex and Qdrant for these queries.

Combine structured and semantic retrieval when the question benefits from both.

Vector similarity alone must never be used to enforce exact numerical constraints.

Never rely on an LLM to calculate exact transaction statistics when a structured query can calculate them.

## 7. Real Estate Data Integrity

The initial real-estate data source is:

https://www.kaggle.com/code/sergionefedov/dubai-real-estate-full-eda-2020-2026/notebook

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

### Milestone 3 — Real Estate Data and Hybrid RAG

Current development milestone.

#### Phase 3A — Dataset investigation
- Inspect Kaggle notebook and underlying dataset.
- Verify licence and attribution.
- Inspect schemas, row counts and date coverage.
- Identify historical versus active inventory records.
- Present a read-only architecture and implementation plan.

#### Phase 3B — Data ingestion and DuckDB
- Build a repeatable CSV ingestion pipeline.
- Validate and normalize source data.
- Preserve source identifiers and provenance.
- Create DuckDB analytical queries.
- Generate data-quality reports.

#### Phase 3C — LlamaIndex and Qdrant
- Set up local Qdrant.
- Implement LlamaIndex integration.
- Select and configure embeddings.
- Design collection and payload schemas.
- Implement indexing and retrieval.
- Make ingestion repeatable and idempotent.

#### Phase 3D — Hybrid retrieval services
- Implement structured query services.
- Implement semantic retrieval.
- Combine retrieval results where useful.
- Test exact filters and semantic relevance.
- Preserve source attribution.

#### Phase 3E — LiveKit integration
- Expose approved retrieval capabilities through Python function tools.
- Integrate historical market intelligence into the receptionist.
- Preserve existing voice functionality.
- Test real voice queries against the data.

Do not treat these phases as permission to implement everything without approval.

### Milestone 4 — Prime Properties business tools and lead qualification
- Buy versus rent intent.
- Customer preference collection.
- Budget qualification.
- Property search against verified active inventory when available.
- Lead capture.
- Structured customer information.

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

Our current objective is Milestone 3: Real Estate Data and Hybrid RAG.

The first task is read-only investigation of the Kaggle dataset.

Before writing code:
1. Inspect the actual repository and Git status.
2. Inspect the Kaggle notebook and underlying dataset.
3. Verify the dataset licence and attribution.
4. Identify which records are useful for market intelligence.
5. Determine which fields support structured DuckDB queries.
6. Determine which information benefits from semantic indexing.
7. Propose the Qdrant collection and payload design.
8. Propose the LlamaIndex ingestion and retrieval design.
9. Identify dependencies and testing requirements.
10. Present the implementation plan and wait for approval.

Do not modify files during the initial investigation.

### Expected first deliverable

A clear, evidence-based implementation plan containing:
- Actual dataset files and schemas.
- Data-quality findings.
- Dataset licence and attribution.
- Proposed ingestion pipeline.
- DuckDB schema and query strategy.
- LlamaIndex and Qdrant architecture.
- Embedding model recommendation.
- Proposed Qdrant collections and payload indexes.
- Dependencies.
- Files to create or modify.
- Testing strategy.

Preserve the completed Milestone 1 and Milestone 2 functionality.

Do not implement CRM, PostgreSQL, authentication, billing, live property feeds or complex dashboards during Milestone 3.

Prioritise reliable data, accurate retrieval, source transparency and a working voice-agent experience.

---

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