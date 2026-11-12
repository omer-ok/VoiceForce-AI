# VoiceForce AI — Milestone 1 Agent Instructions

## Mission

Implement only the following Milestone 1 changes in the existing VoiceForce AI repository:

1. Replace the existing synthetic demo property-listing dataset with exactly 500 synthetic property records:
   - 250 properties for sale.
   - 250 properties for rent.
2. Simplify the receptionist system prompt so the LLM can understand the task and respond naturally with less prompt overhead.
3. Run and validate these changes using the current VoiceForce AI architecture.
4. Ensure the backend remains compatible with Python 3.12 and use asynchronous Python correctly wherever it is beneficial and supported.

This is an implementation task. Inspect the repository, make the changes, run tests, and report evidence. Do not stop after writing a plan.

## 1. Repository inspection and safety

Before editing:

- Read the root `AGENTS.md` and this `AGENT.md`.
- Run `git status --short` and preserve all existing user changes.
- Inspect the current demo listing schema, seed scripts, migrations, repository/data-access layer, property-search tools, receptionist system prompt, configuration, tests and documentation.
- Identify every consumer of the demo listing records before changing their shape or contents.
- Confirm the actual database engine and existing storage conventions. Do not assume a schema or database location.

### Data deletion safety

The request is to clear and recreate the **demo listing records**, not to drop the database or erase unrelated business data.

- Back up/export the existing demo listing records before replacement when the current storage system supports it.
- Delete only records explicitly belonging to the synthetic/demo property-listing dataset (use the existing marker/namespace, such as `is_synthetic`, only after verifying its meaning in the code).
- Never delete historical secondary-sales data, customer leads, production/customer data, database schemas, migrations, or unrelated tables.
- Do not drop or recreate the entire database.
- Perform replacement in a transaction where supported so a failed seed does not leave a partially populated dataset.
- Make the seed operation deterministic and safely repeatable. Re-running it must not create duplicate records.
- If existing records cannot be reliably distinguished as demo listings, stop before destructive deletion and report the ambiguity rather than guessing.

## 2. Demo property dataset — exactly 500 records

Replace the existing demo listing dataset with exactly 500 records.

Required distribution:

| Listing purpose | Required records |
|---|---:|
| Sale | 250 |
| Rent | 250 |
| Total | 500 |

Requirements:

- Reuse the existing `demo_property_listings` table/model and its established schema unless the audit proves a minimal schema correction is required.
- Preserve existing field names and data types consumed by the application.
- Use the existing currency convention (currently expected to be AED; verify it).
- Include realistic synthetic Dubai property data across the communities and property types already supported by the application.
- Populate required search fields consistently: listing purpose, community, property type, bedrooms, bathrooms, price, furnishing and any other required existing fields.
- Preserve the existing synthetic/demo marker and clearly identify all generated records as synthetic.
- Keep generated IDs stable across repeat seed runs if the current schema supports deterministic IDs.
- Use a documented fixed seed so test data can be reproduced.
- Do not describe synthetic records as verified real-world listings.
- Do not invent real-time availability. Preserve the existing simulated/demo availability semantics and make their synthetic nature explicit.
- Ensure sale and rent records are valid for the existing property-search filters and result formatting.

### Dataset validation

After seeding, verify using database queries and tests:

- Total demo listing count is exactly 500.
- Sale count is exactly 250.
- Rent count is exactly 250.
- Every record is marked as synthetic/demo.
- No duplicate IDs or duplicate seed records exist.
- Required fields are populated and valid.
- Existing property search filters return both sale and rent results.
- Pagination/limits and sorting still work.
- Historical-sales queries and lead-capture behavior are unaffected.

Add or update automated tests for these invariants. Do not rely only on printed seed-script output.

## 3. Simplify the receptionist system prompt

Inspect the complete current Prime Properties Dubai receptionist system prompt and all instructions injected into the LLM context.

Create a simpler, shorter prompt that reduces unnecessary input tokens while preserving the agent's actual responsibilities.

The simplified prompt must preserve:

- The receptionist's identity and Prime Properties Dubai context.
- Friendly, natural, professional spoken English.
- Understanding whether the caller wants to buy or rent.
- Asking only necessary clarifying questions.
- Correct use of the existing property-search tool.
- Accurate presentation of listing details returned by the tool.
- The distinction between synthetic demo listings and verified real-world inventory.
- No fabricated prices, availability, property features or search results.
- Lead capture only with explicit customer consent.
- Existing privacy, consent and data-handling requirements.
- All tool permissions and business constraints that are necessary for correctness.

Remove only redundant or low-value prompt content:

- Repeated instructions and duplicated rules.
- Long explanations that can be expressed clearly in one sentence.
- Irrelevant examples and unused role descriptions.
- Static data that is already retrieved through existing tools.
- Unnecessary wording that does not change agent behavior.

Voice response style:

- Respond directly to the caller's question.
- Prefer concise, natural spoken language.
- Avoid repeating the caller's question.
- Avoid unnecessary introductions, filler and lengthy monologues.
- Ask one focused clarification at a time.
- Give enough detail to answer accurately; do not force every response into one sentence.
- Never sacrifice grounding, consent or tool correctness merely to shorten the prompt.

Keep the prompt static and stable where practical. Do not inject changing values into its static prefix without a clear reason.

### Prompt validation

- Record current prompt text/token count using the repository's existing tokenizer or provider usage metrics where available.
- Record simplified prompt text/token count using the same measurement method.
- Compare behavior on identical English test scenarios.
- Test greetings, buying enquiries, rental enquiries, missing filters, no-result searches, property-result summaries and consent-based lead capture.
- Confirm that tool selection, arguments, grounding and consent behavior have not regressed.
- Do not claim lower token counts unless measured.

## 4. Current architecture must remain unchanged

Milestone 1 is an evaluation of the existing architecture with the new dataset and simplified prompt.

Preserve the existing:

- LiveKit Agents integration and session lifecycle.
- Current STT provider and configuration.
- Current LLM provider/model and configuration.
- Current TTS provider and configuration.
- LiveKit transport, token route and browser integration.
- Existing property tools and database architecture.
- Qdrant and DuckDB responsibilities and separation.
- Existing lead-capture workflow and consent handling.
- Existing latency instrumentation.

Do not upgrade or replace the LLM, STT or TTS in this milestone. Do not introduce a new agent framework, database, vector store, cloud service or model-serving architecture.

The purpose is to determine whether a smaller prompt and a clean, balanced 500-record demo dataset improve the current system's behavior and latency before making architecture/model changes in a later milestone.

## 5. Python 3.12 and asynchronous code

Keep the backend compatible with Python 3.12.

- Inspect the project's Python version constraints, dependency manifests and lockfile before modifying them.
- Do not upgrade unrelated dependencies.
- Use `async def` and `await` for I/O operations when the library provides a native async API.
- Do not block the LiveKit event loop with synchronous network, database or filesystem operations.
- For existing synchronous I/O libraries that cannot reasonably be replaced in this milestone, use the established safe thread-offload pattern (for example, `asyncio.to_thread`) and preserve current connection/thread-safety rules.
- Use `asyncio.gather` or `asyncio.TaskGroup` only for genuinely independent operations.
- Do not parallelize dependent operations or duplicate database calls.
- Add sensible timeouts and propagate cancellation correctly.
- Do not swallow `asyncio.CancelledError`.
- Avoid unnecessary async rewrites where the existing code is already correct and non-blocking.
- Keep the current architecture and public tool interfaces stable.

Use Python 3.12-compatible syntax and run the repository's actual linting, formatting, type-checking and test commands.

## 6. Testing and acceptance criteria

Before changes, capture the current relevant baseline where practical:

- Existing demo listing counts and sale/rent distribution.
- Existing system prompt token count.
- Existing property-search test behavior.
- Existing English voice latency metrics if the current instrumentation can capture them without changing providers.

After implementation, run:

1. Database/seed tests.
2. Exact 500-record and 250/250 distribution assertions.
3. Property-search tests for sale and rent.
4. Prompt/token-count comparison.
5. Agent tool-selection and argument tests.
6. Lead-capture consent tests.
7. Existing backend unit and integration tests.
8. Python 3.12 lint/type checks.
9. Existing LiveKit agent/debugger or scenario tests where configured.
10. Browser-based English voice tests using the unchanged current provider stack, where credentials and services are available.

Keep test conditions consistent when comparing before/after latency. Report sample sizes and P50/P90/P95 where enough observations exist. Do not present a tiny sample's maximum as a reliable P95.

### Milestone 1 is complete only when

- The demo listing dataset contains exactly 500 synthetic records.
- There are exactly 250 sale and 250 rent records.
- Only demo listing records were replaced; unrelated data remains intact.
- The receptionist prompt is simpler and its token reduction is measured.
- Property search works for both sale and rent.
- Grounding, synthetic-data labeling and lead-consent rules still work.
- Python 3.12 compatibility is verified.
- Async changes are limited to real I/O/event-loop needs.
- Existing architecture and providers remain unchanged.
- Relevant tests pass, or failures and blockers are clearly documented.

## 7. Final report

When finished, report:

- Initial repository/Git status.
- Database table/model and exact records replaced.
- Backup and deletion safeguards used.
- Seed method and deterministic seed value.
- Final total, sale and rent counts.
- Prompt before/after token counts and a concise summary of changes.
- Files changed.
- Async changes and why each was necessary.
- Python version and test commands/results.
- Property-search and lead-consent regression results.
- Before/after voice latency results, including sample counts and test conditions.
- Known limitations and any tests blocked by unavailable services.

Do not commit or push unless explicitly requested.

## Scope boundary

Only implement the dataset replacement, simplified system prompt, and necessary Python 3.12/async correctness changes for Milestone 1. Do not start LLM model upgrades, STT/TTS migrations, new architecture work or later milestones.
