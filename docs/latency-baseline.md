# VoiceForce AI latency baseline

This document describes the measurement-only latency baseline and telemetry
contract. It does not change AssemblyAI, GPT-5 Mini, VAD, turn detection,
endpointing, WebRTC, or Session API configuration. TTS provider changes are
reported as separate benchmark conditions; the current production route uses
Inworld Realtime TTS-2 Flash for English, Urdu, and Arabic.

## What is measured

The Python worker records one JSON object per metric in:

```text
backend/data/latency_metrics.jsonl
```

The browser records its own JSONL stream through the local Next.js endpoint in:

```text
data/latency_metrics.browser.jsonl
```

Both paths are ignored by Git. New backend records use the unique LiveKit job ID
as `session_id` and keep the room name in `labels.room_name`. New browser
records use one page-session UUID as `session_id` and keep the current LiveKit
room and local participant in labels. The two IDs are intentionally separate;
`room_name` is the cross-domain correlation key when it is available. Backend
records use a process monotonic clock for elapsed values and browser records use
`performance.now()`. These clock domains must not be subtracted from one
another. `speech_id` is included where the LiveKit SDK exposes it; otherwise the
record remains explicitly unlinked.
Transcript text is not stored.

The backend uses the current LiveKit-supported surfaces: per-plugin
`metrics_collected`, `ChatMessage.metrics`, AgentSession state and tool events,
the public VAD and turn-detector objects, and a privacy-conscious
`JobContext.make_session_report()` summary. The browser records microphone
readiness/publication, connection state, remote audio publication/subscription
and unsubscription, media playback status, agent state, and one available
remote audio RTC stats sample.

## Browser event semantics

Browser records prove the following only:

- `start_requested`: the React session start path was invoked.
- `connection_state`, `connected`, and `disconnected`: the LiveKit client
  observed the corresponding room state transition.
- `microphone.ready`: the session hook exposed a local microphone track.
- `microphone.published`: the session hook exposed a microphone track that the
  client considered published; this is not an independent server-side publish
  acknowledgement.
- `remote_track.published`: the client observed an audio track publication.
- `remote_track.subscribed`: the client completed subscription and received a
  remote audio track object; this is not proof that an audio frame was rendered
  or heard. The record includes participant and track identifiers where the
  client exposes them.
- `remote_track.unsubscribed` and `remote_track.subscription_failed`: the
  client observed the corresponding subscription lifecycle event.
- `media_playback.started_or_recovered` and `media_playback.interrupted`:
  LiveKit's room-level audio autoplay status changed. These are not per-turn
  first-audio timestamps and do not prove acoustic playback at the speaker.
- `media_element.can_play`: the app-owned `HTMLAudioElement` reported that it
  can begin playback for a subscribed track.
- `media_element.playing`: the app-owned `HTMLAudioElement` emitted its
  `playing` event. This proves browser media-element playback started or
  resumed for the identified track; it does not prove sound reached the user's
  physical speaker. `media_element.error` records an HTML media error and
  `media_playback.interrupted` records the separate autoplay/status signal.
- `webrtc.remote_audio_jitter` and `webrtc.remote_audio_packets_lost`: one
  inbound RTP statistics sample was available for the subscribed audio track.
- `agent_state.state_changed`: the frontend observed the agent state exposed by
  the LiveKit session hook; it is not an audio playback measurement.

The app now renders the same subscribed remote audio sources through
`AudioTrack`, passing playback and error handlers to the underlying
`HTMLAudioElement`. This is a browser media-element measurement, not an acoustic
loopback measurement. Backend `playback_latency` remains the LiveKit agent-side
metric and must not be interpreted as browser speaker latency.

## Run a local baseline

Start the worker and frontend independently:

```bash
cd backend
uv sync
lk agent dev --deployment dev
```

```bash
npm run dev
```

For each benchmark condition, use a fresh browser session and complete at least
30 measured user turns. Start with these conditions:

1. normal English conversation;
2. fast speech;
3. slow speech;
4. short acknowledgements;
5. laptop microphone and speakers;
6. headset microphone and speakers;
7. noisy environment;
8. interruption or barge-in;
9. English/Urdu code switching;
10. a property search tool call;
11. a cold worker/session;
12. a warm worker/session.

Do not include the initial greeting in turn-level latency samples unless it is
being measured as a separate cold-start condition. Record the condition and
browser/audio setup outside the JSONL file so the same metric is not mixed
across materially different test environments.

Summarize one or both local files with:

```bash
cd backend
uv run python scripts/summarize_latency.py \
  --input data/latency_metrics.jsonl \
  --input ../data/latency_metrics.browser.jsonl
```

To isolate one new backend job without mixing historical records, first list
session IDs from the JSONL or the report, then run:

```bash
uv run python scripts/summarize_latency.py \
  --input data/latency_metrics.jsonl \
  --input ../data/latency_metrics.browser.jsonl \
  --session-id <livekit-job-id> \
  --diagnostic
```

Use `--turn-id`, `--speech-id`, or `--room-name` for narrower correlation. The
summary reports sample count alongside every percentile, observation counts for
available and missing turn metrics, separate per-component and per-turn
aggregates, and chronological diagnostics only for records with explicit IDs.
Missing or incomplete metrics remain null and are never treated as zero. Backend
and browser timelines remain separate by clock domain; the report never derives
an E2E value by summing overlapping components.

The six controlled benchmark scenario definitions are in
`backend/scenarios/voice_latency_benchmark.yaml`. For debugger audio runs, keep
the scenario's spoken turns fixed and record the scenario tag, cold/warm status,
language, noise condition, and audio mode beside the isolated session report.

## Baseline report

Do not copy aggregate historical numbers into a session-specific result. The
local JSONL currently contains records from multiple older sessions, including
room names that were reused before job IDs became backend session IDs. Therefore
the table below must be generated from a filtered, fresh session after the P1
instrumentation is exercised:

| Metric | Count | Min | Mean | P50 | P90 | P95 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| STT/transcription delay | — | — | — | — | — | — | — |
| EOU/EOT delay | — | — | — | — | — | — | — |
| LLM TTFT | — | — | — | — | — | — | — |
| TTS TTFB | — | — | — | — | — | — | — |
| browser media playback | — | — | — | — | — | — | — |
| end-to-end | — | — | — | — | — | — | — |
| tool duration | — | — | — | — | — | — | — |

Populate this table only from fresh records generated with this instrumentation.
The earlier pre-instrumentation worker log is not treated as the Phase 1
baseline.

## Interpretation rules

- `llm_ttft` is the LiveKit LLM metric, not browser time to first audio.
- `tts_ttfb` is provider/pipeline time to first synthesized audio byte.
- `media_playback.started_or_recovered` is the public room playback-status
  event, not proof of audible output at the user's physical speaker.
- `e2e_latency` comes from the agent turn metrics where available and must not
  be recomputed from backend and browser timestamps.
- `end_of_turn_delay` already describes the end-of-speech-to-turn-decision
  component. `transcription_delay` is reported independently and must not be
  added to it.
- `media_element.playing` is the first owned HTML media-element playback event,
  not a claim that the caller acoustically heard the audio.
- A missing provider metric is reported as unavailable; it is never silently
  estimated.

The diagnostic report explicitly marks request-start, first-sentence, first
forwarded-frame, and browser stages as missing when the current public SDK or
architecture does not expose a reliable event for them. Provider TTFB/TTFT
durations and LiveKit per-turn E2E are retained as their documented measurements
and are not converted into invented absolute timestamps.

Historical aggregate figures may still be summarized for context, but they must
be labeled aggregate historical results and must not be attributed to a single
debugger session.

## Official LiveKit references

- [Agent events](https://docs.livekit.io/reference/agents/events)
- [Session traces and metrics](https://docs.livekit.io/reference/agents/session-traces)
- [Metrics and usage data](https://docs.livekit.io/testing/observability/data)
- [Agent insights](https://docs.livekit.io/testing/observability/insights)
