# VoiceForce AI

VoiceForce AI is a real-time AI voice receptionist for Prime Properties Dubai.
The current product can connect a browser caller to a Python LiveKit Agent,
publish microphone audio, play the agent response, and display live
conversation transcripts.

## Current status

- Milestone 1 — Python LiveKit Agent backend: completed and committed.
- Milestone 2 — Next.js browser-to-agent integration: completed and committed.
- Milestone 3 — Historical property sales intelligence: initial implementation
  completed for one Kaggle CSV; semantic retrieval remains deferred.
- Milestone 4 — AI property sales agent: backend implementation complete; live
  voice smoke testing remains environment-dependent.
- Multilingual voice routing: English, Urdu, and Arabic welcome selection is
  implemented with per-session language persistence and runtime TTS switching.
- Voice latency telemetry: backend per-turn metrics, isolated session reports,
  browser media-element events, and controlled debugger scenarios are
  implemented. The current measurements are engineering observations, not a
  release acceptance benchmark.

CRM tools, authentication, PostgreSQL, billing, live authoritative property
feeds, appointment scheduling, and dashboards remain planned work.

## Architecture

The browser uses the LiveKit Session API. When a caller starts a call, the
Next.js server route creates a short-lived participant token, validates the
requested agent dispatch, and embeds the `voiceforce-receptionist` dispatch in
the token's `room_config`. The browser then connects to LiveKit Cloud,
publishes microphone audio, subscribes to agent audio, and receives
transcripts.

The Python backend registers the same named agent with `AgentServer` and uses
`AgentSession` with LiveKit Inference for:

- STT: AssemblyAI Universal-3-6-Pro.
- LLM: OpenAI GPT-5.6 Terra through LiveKit Inference for the latest local
  latency test. The configurable default is GPT-5 Mini.
- TTS: Inworld Realtime TTS-2 Flash through LiveKit Inference.

The receptionist has three historical-data tools backed by DuckDB:
`search_historical_sales`, `get_market_insights`, and `compare_areas`. It also
has `search_demo_properties` for the 500-record synthetic AED inventory and
`capture_customer_lead` for consent-gated demo enquiries. Historical results
remain clearly labelled as historical dataset records, while demo results are
clearly labelled as synthetic with simulated availability.

Milestone 3 currently uses only `secondary_sales.csv` from the Kaggle dataset.
The source documentation describes the records as generated for analysis, not
as verified Dubai Land Department transactions. The ingestion provenance table
preserves both licence statements: Apache 2.0 in Kaggle metadata and CC0 / Public
Domain in the dataset description. The conflict remains unresolved, and
commercial-use clearance has not been established.
All source price fields and calculated price-per-area fields are in USD; no
currency conversion is performed.

## Technology stack

- Next.js 16 App Router, React, TypeScript, and Tailwind CSS.
- LiveKit React Components and LiveKit Client SDK.
- LiveKit Cloud, WebRTC rooms, and named agent dispatch.
- Python 3.10–3.14, LiveKit Agents, `AgentServer`, and `AgentSession`.
- LiveKit Inference for STT, LLM, and TTS.

The STT is configured for AssemblyAI Universal-3.6 Pro multilingual detection.
All three response languages use Inworld Realtime TTS-2 Flash through LiveKit
Inference after the caller's STT language metadata identifies a supported
language. The voice IDs are deployment configuration, not hardcoded guesses.

The active language routes are:

| Language | STT language | TTS provider/model | Voice | Locale |
| --- | --- | --- | --- | --- |
| English | `en` | Inworld Realtime TTS-2 Flash (`inworld/inworld-tts-2-flash`) | Simon | `en` (catalog: `en-US`) |
| Urdu | `ur` | Inworld Realtime TTS-2 Flash (`inworld/inworld-tts-2-flash`) | Aarav | `ur-PK` |
| Arabic | `ar` | Inworld Realtime TTS-2 Flash (`inworld/inworld-tts-2-flash`) | Omar | `ar-SA` |

The browser welcome flow plays one concise English language-selection prompt
and hands the same `AgentSession` to the selected receptionist. Urdu responses
are requested as Urdu rather than Hindi, and Arabic/Urdu language state is
preserved for the session while still allowing deliberate language switches.

- Planned retrieval architecture: DuckDB, LlamaIndex, and Qdrant.

Retrieval responsibilities are intentionally separated:

- DuckDB is mandatory for historical sales, rental, and market analytics.
- Future live availability must come from a separate authoritative inventory
  source.
- LlamaIndex orchestrates semantic retrieval and does not calculate exact
  numerical results.
- Qdrant stores semantic vectors and supports metadata filtering; it is not a
  source of truth for current property availability.

## Repository structure

```text
.
├── app/
│   ├── api/token/route.ts       # Server-side LiveKit token endpoint
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx                 # VoiceForce landing and call page
├── components/
│   ├── voiceforce-call.tsx      # Session API call controls and transcripts
│   ├── voiceforce-latency.tsx    # Browser media and LiveKit telemetry
│   └── voiceforce-call-loader.tsx
├── backend/
│   ├── src/agent.py             # Python CLI entrypoint
│   ├── src/voiceforce_agent/
│   │   ├── config.py            # LiveKit Inference configuration
│   │   ├── language_router.py    # Per-session language and TTS routing
│   │   ├── latency_metrics.py    # Privacy-conscious backend telemetry
│   │   ├── lead_storage.py      # Consent-gated demo lead persistence
│   │   ├── property_search.py   # Parameterized synthetic inventory queries
│   │   ├── receptionist.py      # Sales consultant and function tools
│   │   ├── sales_data.py         # Dataset identity and schema constants
│   │   ├── sales_ingestion.py    # Pandas validation and DuckDB ingestion
│   │   ├── sales_queries.py      # Parameterized historical sales queries
│   │   ├── server.py             # AgentServer and AgentSession
│   │   ├── state.py              # Per-session structured preferences
│   │   └── welcome.py            # Multilingual welcome and selection flow
│   ├── tests/
│   │   ├── test_configuration.py
│   │   ├── test_language_router.py
│   │   ├── test_latency_metrics.py
│   │   ├── test_lead_storage.py
│   │   ├── test_property_search.py
│   │   └── test_sales_queries.py
│   ├── scripts/
│   │   ├── generate_demo_listings.py
│   │   └── summarize_latency.py
│   ├── scenarios/
│   │   └── voice_latency_benchmark.yaml
│   ├── data/                     # Generated DuckDB; ignored by Git
│   ├── pyproject.toml
│   └── uv.lock
├── next.config.ts
├── package.json
└── tsconfig.json
```

The complete telemetry semantics and benchmark workflow are documented in
[`docs/latency-baseline.md`](docs/latency-baseline.md). Backend and browser
telemetry use separate clock domains. A browser `HTMLAudioElement` `playing`
event proves media-element playback started, but it is not an acoustic
loopback measurement and does not prove that sound reached the caller's
physical speaker.

## Prerequisites

- Node.js and npm.
- Python 3.10 through 3.14.
- [`uv`](https://docs.astral.sh/uv/).
- The LiveKit CLI (`lk`).
- A LiveKit Cloud project with credentials.
- A browser with microphone access.

## Environment variables

Create the repository-root `.env.local` file with the required LiveKit names
and any desired optional settings below. Keep its values private; it is
excluded from Git.

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
NEXT_PUBLIC_LIVEKIT_URL
VOICEFORCE_LLM_MODEL
VOICEFORCE_LLM_REASONING_EFFORT
VOICEFORCE_LLM_MAX_COMPLETION_TOKENS
VOICEFORCE_PREEMPTIVE_TTS
VOICEFORCE_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS
VOICEFORCE_PREEMPTIVE_TTS_MAX_RETRIES
VOICEFORCE_FAST_PROPERTY_RESULTS
VOICEFORCE_INWORLD_MODEL
VOICEFORCE_INWORLD_ENGLISH_VOICE
VOICEFORCE_INWORLD_URDU_VOICE
VOICEFORCE_INWORLD_ARABIC_VOICE
```

The LLM and latency settings are optional; see `backend/.env.example` for
defaults. `VOICEFORCE_FAST_PROPERTY_RESULTS` is `false` by default and can be
set to `true` for an experimental local test. Restart the backend after changing
its environment.

The Python backend and Next.js token route read the server-side LiveKit
credentials from the root environment file. The browser does not receive
`LIVEKIT_API_SECRET`. The current Session API obtains the LiveKit server URL
from the token endpoint rather than constructing a token in browser code.

## Run the backend

From the repository root:

```bash
set -a
source .env.local
set +a
cd backend
uv sync
python -m voiceforce_agent.sales_ingestion \
  --input /path/to/secondary_sales.csv \
  --database data/voiceforce.duckdb
uv run python scripts/generate_demo_listings.py
lk agent dev --deployment dev
```

The backend registers the `voiceforce-receptionist` agent. The explicit `dev`
deployment matches the local Next.js Session configuration.

The generator creates or refreshes the local `demo_property_listings` table
through the canonical `property_records` table. On a legacy database, run the
normalization migration before the generator:

```bash
cd backend
uv run python scripts/migrate_property_records.py
uv run python scripts/generate_demo_listings.py
```

The migration exports both legacy source tables, preserves `demo_leads` and
`dataset_provenance`, and replaces the source table names with read-only
compatibility views.

## Run the frontend

In a separate terminal from the repository root:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Test a browser voice conversation

1. Start the backend with `lk agent dev --deployment dev`.
2. Start the frontend with `npm run dev`.
3. Open the local app and click **Start Call**.
4. Allow microphone access when prompted.
5. Speak naturally in English. The receptionist should greet you, respond
   with audio, and display the conversation transcript.
6. To test Urdu or Arabic, set the corresponding Inworld voice variable in the
   backend environment, restart the backend, and speak in the target language.
   Select voices recorded or evaluated for the target language in the Inworld
   TTS Playground; the application does not guess voice IDs.
7. Ask to buy or rent, provide a community and budget, and request demo
   property recommendations. Sale amounts are purchase prices in AED; rental
   amounts are annual rent in AED.
8. If you want an enquiry registered, explicitly consent, confirm your name and
   phone number, and then let the agent save the demo enquiry.
9. Click **End Call** to disconnect.

The token route accepts the Session API's `room_config`, validates the agent
name and deployment, and uses that validated configuration for LiveKit agent
dispatch. There is no separate manual dispatch mechanism in the frontend.

## Voice latency and optimization status

The latest manual English browser call was recorded on **13 November 2026**
using AssemblyAI STT, GPT-5.6 Terra (`reasoning_effort=none`), Inworld TTS,
STT endpointing, and the experimental fast-result path enabled. These are
engineering observations from one call, not a controlled benchmark.

| Measurement | Latest call | Interpretation |
| --- | --- | --- |
| Backend end-to-end | 1.71, 1.80, 3.66, 4.38 s (`N=4`) | Two responses exceeded 3 s; the 3.66 s response was interrupted. The fast-result reply had no available backend E2E measurement. |
| LLM time to first token | 1.12–1.55 s (`N=4`) | Per-turn backend LLM metric; not caller-heard latency. |
| TTS time to first audio | 0.32–0.94 s (`N=5`) | Provider/pipeline metric; includes one 0.94 s outlier. |
| Database query duration | 0.016–0.365 s (`N=3`) | The two no-result searches took about 0.016–0.017 s each. |
| Browser speech-end to remote signal | 1.06, 3.98, 4.62 s (`N=3`) | Uncalibrated signal estimates; they cannot reliably distinguish an acknowledgement from the answer or prove speaker playback. |

For context, an earlier call with the fast-result candidate disabled recorded
21 backend E2E responses: P50 **4.15 s**, P90 **5.84 s**, P95 **6.54 s**,
maximum **8.42 s**, and **17 responses over 3 s**. The report uses nearest-rank
percentiles. The latest call had only four E2E samples, so its tail cannot be
estimated reliably; the different calls and scenarios do not establish a
before-and-after speedup. Browser and backend clocks are separate and must not
be subtracted from one another.

Changes implemented to reduce latency and improve visibility:

- Replaced the six-part welcome with one concise language-selection prompt.
- Configured AssemblyAI's low-latency STT mode and STT-based turn detection,
  with no additional LiveKit endpointing delay. Reported STT/end-of-turn
  timings are SDK metrics, not an acoustic stopwatch.
- Added configurable LLM selection and reasoning effort, bounded preemptive TTS,
  and shorter conversational context. The tested Terra configuration is an
  environment setting; GPT-5 Mini remains the code default.
- Added a short, interruptible search acknowledgement and an **opt-in**
  grounded template for a qualifying single demo result. It retains the
  search result for follow-up and states that availability is simulated. The
  template ran once in the latest call, but its caller-heard answer latency was
  not reliably measured. General questions, ambiguous requests, no-result
  searches, historical analysis, and lead capture use the existing path.
- Added per-response slow-turn records and explicit LiveKit speech, chat-item,
  and tool-call links where available. The browser also records an independent
  signal estimate; missing correlations remain unavailable.

The two slowest measured responses in the latest call were no-result searches,
which still require a model-generated follow-up after the database lookup.
Reducing that additional model work and investigating the TTS outlier are
next steps. The fast-result candidate has **not** met its promotion gates:
the required controlled audio comparison and browser detector calibration
remain incomplete after the simulated-caller TTS request received HTTP 429.
The current data does not demonstrate a consistent sub-3-second response.

To reproduce an isolated backend report without mixing historical records:

```bash
cd backend
uv run python scripts/summarize_latency.py \
  --input data/latency_metrics.jsonl \
  --session-id <livekit-job-id> \
  --diagnostic
```

The benchmark scenarios are defined in
[`backend/scenarios/voice_latency_benchmark.yaml`](backend/scenarios/voice_latency_benchmark.yaml).
See [`docs/latency-baseline.md`](docs/latency-baseline.md) for metric semantics
and the measurement workflow.

### Historical language-route debugger observations

The following is an earlier local audio-mode debugger measurement for the
three selected language routes. It used one fresh session per route and two
steady-state receptionist turns after the language-selection handoff. The
sample is too small for release or production P95 claims.

`P0` is shown as the minimum observed value and `P100` as the maximum. Values
are seconds. The percentile implementation uses nearest-rank selection, so with
`N=2`, P50 is the lower observation and P90/P95 are the upper observation.

| Stage | English / Fish baseline (`N=2`) | Urdu / Aarav (`N=2`) | Arabic / Omar (`N=2`) |
| --- | ---: | ---: | ---: |
| End-to-end (`e2e_latency`) | 3.154 / 3.154 / 3.568 / 3.568 / 3.568 | 2.960 / 2.960 / 4.500 / 4.500 / 4.500 | 2.620 / 2.620 / 3.031 / 3.031 / 3.031 |
| End-of-turn (`end_of_turn_delay`) | 0.784 / 0.784 / 0.927 / 0.927 / 0.927 | 0.820 / 0.820 / 2.501 / 2.501 / 2.501 | 0.693 / 0.693 / 0.785 / 0.785 / 0.785 |
| Transcription (`transcription_delay`) | 0.772 / 0.772 / 0.915 / 0.915 / 0.915 | 0.806 / 0.806 / 0.948 / 0.948 / 0.948 | 0.679 / 0.679 / 0.770 / 0.770 / 0.770 |
| LLM TTFT (`llm_node_ttft`) | 1.659 / 1.659 / 1.938 / 1.938 / 1.938 | 1.538 / 1.538 / 3.101 / 3.101 / 3.101 | 1.341 / 1.341 / 1.861 / 1.861 / 1.861 |
| LLM TTFS (`llm_node_ttfs`) | 1.835 / 1.835 / 2.108 / 2.108 / 2.108 | 1.666 / 1.666 / 3.351 / 3.351 / 3.351 | 1.511 / 1.511 / 2.044 / 2.044 / 2.044 |
| TTS TTFB (`tts_node_ttfb`) | 0.543 / 0.543 / 0.545 / 0.545 / 0.545 | 0.341 / 0.341 / 0.344 / 0.344 / 0.344 | 0.306 / 0.306 / 0.336 / 0.336 / 0.336 |

Column order is `P0 / P50 / P90 / P95 / P100`. The fresh debugger session
identifiers were `mock-job-fa8395c2def8` (English), `mock-job-4f6eb5f0a2a1`
(Urdu), and `mock-job-33b92203f3f3` (Arabic). These records were filtered by
session and were not mixed with historical JSONL records.

The separate cold/session-start observations were:

| Cold sequence | English | Urdu | Arabic |
| --- | ---: | ---: | ---: |
| Previous six-segment welcome sequence (`N=1`) | 43.930s | 41.582s | 44.360s |
| Language-selection handoff E2E (`N=1`) | 10.379s | 7.234s | 6.325s |

These cold values are not normal conversational-turn measurements. No property
search tool or database query was executed in this three-route sample, so it
does not provide a database or property-search latency result. Backend
`playback_latency` was recorded separately, but it must not be interpreted as
browser audible playback.

The post-migration English Simon smoke measurement used the same spoken
sentence, `I need help finding a property.`, in a fresh audio debugger session.
It is one normal receptionist turn (`N=1`) and is therefore directional only:

| Metric | Fish baseline P50 (`N=2`) | Inworld Simon (`N=1`) | Observed change |
| --- | ---: | ---: | ---: |
| End-to-end | 3.154s | 2.473s | -0.681s |
| LLM TTFT | 1.659s | 1.357s | -0.302s |
| TTS TTFB | 0.543s | 0.327s | -0.216s |

This is not a provider-quality conclusion: the Fish values have two normal
turns while Simon has one, and browser playback was not measured. The Simon
session did emit audio through the configured LiveKit route, with backend logs
confirming `inworld/inworld-tts-2-flash`, voice `Simon`, and locale `en`.

The historical evidence points to the LLM as the largest steady-state latency
component. The English values in this table are the old Fish Audio baseline;
the post-migration Simon comparison is shown above from a fresh session with
the new route. Urdu's second turn contained a synthetic-input STT anomaly and
should not be treated as a clean language-quality comparison. Larger controlled
runs are required before drawing a provider-quality conclusion or changing
turn-taking settings.

To reproduce an isolated report without mixing historical records:

```bash
cd backend
uv run python scripts/summarize_latency.py \
  --input data/latency_metrics.jsonl \
  --session-id <livekit-job-id> \
  --diagnostic
```

The controlled scenarios are defined in
[`backend/scenarios/voice_latency_benchmark.yaml`](backend/scenarios/voice_latency_benchmark.yaml).
They cover greeting/clarification, one-tool property search, no results,
rental-to-sale correction, clearing a budget, and a longer multi-result
response. Each benchmark should record sample counts, cold/warm status, audio
mode, language, and noise condition.

## Milestone 3 scope and roadmap

The implemented initial slice uses only `secondary_sales.csv` from the [Dubai
real-estate dataset and Kaggle notebook](https://www.kaggle.com/code/sergionefedov/dubai-real-estate-full-eda-2020-2026/notebook):

1. Verify the selected CSV schema, dates, data quality, licence, and
   attribution.
2. Run repeatable Pandas validation and DuckDB ingestion outside the agent
   startup path.
3. Query historical sales by area, property type, bedrooms, price, date, and
   time trend.
4. Expose historical sales search, market insights, and area comparison through
   LiveKit Python tools.

Historical dataset records and recorded dataset prices must never be presented
as active listings or current asking prices. An authoritative live inventory
source is required before the agent can claim current availability.

The following remain explicitly deferred: other Kaggle CSV files, Dubai Land
Department integration, external datasets, Qdrant deployment, LlamaIndex
indexing, embeddings, advanced hybrid search, PostgreSQL, authentication, CRM,
and billing. DuckDB remains responsible for exact numerical historical
analytics and the synthetic demo inventory lookup; Qdrant and LlamaIndex are
future semantic-retrieval components.

## Milestone 4 demo sales scope

The current sales consultant uses the canonical local `property_records` table
with a synthetic-demo source filter. It supports buy-versus-rent intent,
community, property type, bedroom and bathroom count, AED budget, furnishing,
and result selection. The actual demo schema has no ready/off-plan field, so
that preference is recorded but not used as a filter.

All 500 records are synthetic and illustrative: 250 are sale records and 250
are rental records. The generator uses a fixed seed and backs up the existing
marked demo rows before replacement. Simulated availability is not verified
live inventory, and no result should be represented as a genuine listing or
current offer. Canonical storage also contains 50,000 historical sale records;
historical analytics remain source-scoped, use native USD prices, and never
appear in demo availability searches. Lead capture writes to a separate
`demo_leads` table only after explicit customer consent and confirmation of the
name and phone number.
