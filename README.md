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

Property search, CRM tools, authentication, PostgreSQL, billing, live
property feeds, and dashboards are planned work. They are not implemented.

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
- LLM: OpenAI GPT-5 Mini.
- TTS: Fish Audio S2.1 Pro.

The receptionist now has three historical-data tools backed by DuckDB:
`search_historical_sales`, `get_market_insights`, and `compare_areas`. It
clearly labels their results as historical dataset records and cannot verify
live property availability.

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
│   └── voiceforce-call-loader.tsx
├── backend/
│   ├── src/agent.py             # Python CLI entrypoint
│   ├── src/voiceforce_agent/
│   │   ├── config.py            # LiveKit Inference configuration
│   │   ├── receptionist.py      # Receptionist and historical-data tools
│   │   ├── sales_data.py         # Dataset identity and schema constants
│   │   ├── sales_ingestion.py    # Pandas validation and DuckDB ingestion
│   │   ├── sales_queries.py      # Parameterized historical sales queries
│   │   └── server.py             # AgentServer and AgentSession
│   ├── tests/
│   │   ├── test_configuration.py
│   │   └── test_sales_queries.py
│   ├── data/                     # Generated DuckDB; ignored by Git
│   ├── pyproject.toml
│   └── uv.lock
├── next.config.ts
├── package.json
└── tsconfig.json
```

## Prerequisites

- Node.js and npm.
- Python 3.10 through 3.14.
- [`uv`](https://docs.astral.sh/uv/).
- The LiveKit CLI (`lk`).
- A LiveKit Cloud project with credentials.
- A browser with microphone access.

## Environment variables

Create the repository-root `.env.local` file with the required names below.
Keep its values private; it is excluded from Git.

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
NEXT_PUBLIC_LIVEKIT_URL
```

The Python backend and Next.js token route read the server-side LiveKit
credentials from the root environment file. The browser does not receive
`LIVEKIT_API_SECRET`. The current Session API obtains the LiveKit server URL
from the token endpoint rather than constructing a token in browser code.

## Run the backend

From the repository root:

```bash
cd backend
uv sync
python -m voiceforce_agent.sales_ingestion \
  --input /path/to/secondary_sales.csv \
  --database data/voiceforce.duckdb
lk agent dev --deployment dev
```

The backend registers the `voiceforce-receptionist` agent. The explicit `dev`
deployment matches the local Next.js Session configuration.

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
6. Click **End Call** to disconnect.

The token route accepts the Session API's `room_config`, validates the agent
name and deployment, and uses that validated configuration for LiveKit agent
dispatch. There is no separate manual dispatch mechanism in the frontend.

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
analytics; Qdrant and LlamaIndex are future semantic-retrieval components.
