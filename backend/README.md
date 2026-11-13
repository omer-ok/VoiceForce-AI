# VoiceForce AI LiveKit Agent

This directory contains the Python LiveKit Agent backend. It is independent of
the Next.js frontend and uses LiveKit Inference for speech-to-text, language
model, and text-to-speech services.

## Requirements

- Python 3.10 through 3.14
- `uv`
- A LiveKit Cloud project

The backend reads `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`
from the repository root `.env.local`. Do not create a second credential file
or expose these values to the browser.

The conversational LLM is configured through LiveKit Inference. The safe
fallback is GPT-5 Mini; the same settings can be overridden for controlled
latency comparisons with `openai/gpt-5.6-terra` or `openai/gpt-5.6-luna`:

```text
VOICEFORCE_LLM_MODEL=openai/gpt-5-mini
VOICEFORCE_LLM_REASONING_EFFORT=low
VOICEFORCE_LLM_MAX_COMPLETION_TOKENS=256
```

The LLM model ID is fully qualified and no separate OpenAI API key is needed.
The reasoning effort and completion cap are recorded with local latency
telemetry so candidate runs can be compared without mixing configurations.
Optional benchmark labels are read from `VOICEFORCE_BENCHMARK_RUN_ID`,
`VOICEFORCE_BENCHMARK_SCENARIO`, `VOICEFORCE_BENCHMARK_COLD_WARM`,
`VOICEFORCE_BENCHMARK_LANGUAGE`, and `VOICEFORCE_BENCHMARK_AUDIO_MODE`.

AssemblyAI Universal-3.6 Pro is configured for English, Urdu, Arabic, and
supported code-switching through provider language detection. The low-latency
STT endpointing mode owns turn completion, with LiveKit's additive endpointing
delay disabled and Silero VAD aligned to AssemblyAI's threshold. English keeps the
Inworld Realtime TTS-2 Flash through LiveKit Inference is used for all three
response languages. Configure the validated English system voice Simon and the
selected Urdu and Arabic voices with:

```text
VOICEFORCE_INWORLD_MODEL=inworld/inworld-tts-2-flash
VOICEFORCE_INWORLD_ENGLISH_VOICE=Simon
VOICEFORCE_INWORLD_URDU_VOICE=Aarav
VOICEFORCE_INWORLD_ARABIC_VOICE=Omar
```

The application forwards `en`, `ur-PK`, and `ar-SA` as the TTS language values.
These are voice IDs, not LiveKit or Inworld API keys; LiveKit Inference uses the
existing LiveKit Cloud credentials. Do not replace the qualified model ID with
the unqualified direct-Inworld-plugin identifier.

## Install

From this directory:

```bash
uv sync
```

## Run locally

Run the agent in development mode so it can be reached from LiveKit Cloud:

```bash
set -a
source ../.env.local
set +a
lk agent dev --deployment dev
```

The environment file lives at the repository root. Load it explicitly when
starting from this directory so the worker and the Next.js token route use the
same LiveKit project and `dev` deployment.

You can also run the entrypoint directly:

```bash
uv run src/agent.py dev
```

The registered agent name is `voiceforce-receptionist`.

Before testing the sales-consultant flow, generate the reproducible synthetic
inventory after normalizing an existing legacy DuckDB file:

```bash
uv run python scripts/migrate_property_records.py
uv run python scripts/generate_demo_listings.py
```

## Historical sales data

Milestone 3 currently uses only the Kaggle `secondary_sales.csv` file. Keep
the raw CSV outside Git, then ingest it from this directory:

```bash
python -m voiceforce_agent.sales_ingestion \
  --input /path/to/secondary_sales.csv \
  --database data/voiceforce.duckdb
```

The generated DuckDB file is ignored by Git. The ingestion command validates
the schema, normalizes types, removes exact duplicates and duplicate source
IDs, drops invalid required records, and writes the historical subset to the
canonical `property_records` table. The receptionist exposes historical sales
search, market-insight, and area-comparison tools; these results are not live
property availability.
All source price fields and calculated price-per-area fields are in USD; no
currency conversion is performed.

The source documentation describes the records as generated for analysis, not
as verified Dubai Land Department transactions. Provenance preserves both
licence statements: Apache 2.0 in Kaggle metadata and CC0 / Public Domain in
the dataset description. The conflict remains unresolved, and commercial-use
clearance has not been established.

To test multilingual speech, set the voice IDs in the repository-root
`.env.local`, restart the agent, and speak a controlled English, Urdu, or
Arabic property enquiry. The router uses AssemblyAI's language metadata and
switches TTS at the synthesis boundary; it does not add a separate language-
detection LLM request. Language events and provider/model labels are recorded
without storing transcripts.

## Canonical property records and synthetic demo inventory

`property_records` is the canonical DuckDB table. The normalized database
contains 50,000 historical secondary-sale transactions plus 500 synthetic demo
records: 250 sale records and 250 rent records. Historical prices remain USD
with `transaction_price`; demo prices remain AED with `purchase_price` or
`annual_rent`. Historical rows are marked unavailable and unverified, while
demo availability remains explicitly simulated.

The migration exports both legacy source tables before replacing them with
read-only compatibility views named `secondary_sales` and
`demo_property_listings`. The generator uses fixed seed `20251105`, replaces
only canonical rows marked as `synthetic_demo_listing`, and is idempotent. The
sales consultant queries the canonical table with a demo-only source filter;
historical analytics use a historical-only source filter. The demo schema does
not contain a ready/off-plan field, so that preference is recorded but not
applied as a search filter.

The `capture_customer_lead` tool creates the separate `demo_leads` table on
first use and stores an enquiry only after explicit customer consent and
confirmation of the customer's name and phone number. It validates selected
IDs against canonical synthetic demo rows and does not modify
`dataset_provenance`.

Run backend checks from this directory:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```
