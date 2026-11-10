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

AssemblyAI Universal-3.6 Pro is configured for English, Urdu, Arabic, and
supported code-switching through provider language detection. English keeps the
existing Fish Audio TTS. Urdu and Arabic use Inworld Realtime TTS-2 Flash. Set
`VOICEFORCE_INWORLD_URDU_VOICE` and
`VOICEFORCE_INWORLD_ARABIC_VOICE` to native-language voice IDs selected from
the Inworld TTS catalog/playground. These are not LiveKit or Inworld API keys;
LiveKit Inference uses the existing LiveKit Cloud credentials.

## Install

From this directory:

```bash
uv sync
```

## Run locally

Run the agent in development mode so it can be reached from LiveKit Cloud:

```bash
lk agent dev --deployment dev
```

You can also run the entrypoint directly:

```bash
uv run src/agent.py dev
```

The registered agent name is `voiceforce-receptionist`.

Before testing the sales-consultant flow, generate the reproducible synthetic
inventory if the local DuckDB file does not already contain it:

```bash
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
IDs, drops invalid required records, preserves the source `id`, and records
source provenance. The receptionist exposes historical sales search,
market-insight, and area-comparison tools; these results are not live property
availability.
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

## Synthetic demo property sales

The `demo_property_listings` table contains 100 reproducible synthetic records
in AED, split between illustrative sale prices and annual rental amounts. The
sales consultant searches this table with parameterized filters and returns
only records marked `is_synthetic = true` with `simulated_*` availability.
These are not genuine listings or verified current inventory. The demo schema
does not contain a ready/off-plan field, so that preference is not applied as a
search filter.

The `capture_customer_lead` tool creates the separate `demo_leads` table on
first use and stores an enquiry only after explicit customer consent and
confirmation of the customer's name and phone number. It does not modify
`secondary_sales` or `dataset_provenance`.

Run backend checks from this directory:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```
