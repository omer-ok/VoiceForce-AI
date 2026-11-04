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
lk agent dev
```

You can also run the entrypoint directly:

```bash
uv run src/agent.py dev
```

The registered agent name is `voiceforce-receptionist`.
