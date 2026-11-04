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
