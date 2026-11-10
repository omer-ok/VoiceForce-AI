"""Lightweight, local latency telemetry for the VoiceForce baseline.

The recorder deliberately keeps backend and browser clocks separate.  Records
contain wall-clock timestamps for inspection and monotonic timestamps for
elapsed durations measured inside one process.  No record contains transcript
text or other conversational content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livekit.agents import ToolCallEnded, ToolCallStarted, ToolReplyUpdated
from livekit.agents.llm import ChatMessage

logger = logging.getLogger(__name__)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_METRICS_PATH = _REPOSITORY_ROOT / "backend" / "data" / "latency_metrics.jsonl"
_MISSING = object()


def default_metrics_path() -> Path:
    """Return the local JSONL destination without creating it."""

    configured = os.getenv("VOICEFORCE_LATENCY_METRICS_PATH")
    return Path(configured).expanduser() if configured else _DEFAULT_METRICS_PATH


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_available(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return False
    return not (isinstance(value, (int, float)) and value < 0)


def _turn_metric_value(metrics: Mapping[str, Any], field_name: str) -> Any:
    """Return a validated value from the SDK's dictionary-backed MetricsReport."""

    value = metrics.get(field_name)
    if value is None:
        return None

    if field_name == "provider_request_ids":
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(float(value)) or value < 0:
            return None
    except (OverflowError, TypeError, ValueError):
        return None
    return value


def make_metric_record(
    *,
    session_id: str,
    stage: str,
    metric: str,
    value: Any = None,
    unit: str,
    source: str,
    turn_id: str | None = None,
    speech_id: str | None = None,
    request_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    labels: Mapping[str, Any] | None = None,
    available: bool | None = None,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    """Create a serializable record with explicit units and availability."""

    record: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "metric",
        "session_id": session_id,
        "turn_id": turn_id,
        "speech_id": speech_id,
        "request_id": request_id,
        "timestamp": _timestamp(),
        "monotonic_seconds": time.monotonic(),
        "clock_domain": "backend_process",
        "stage": stage,
        "metric": metric,
        "value": value,
        "unit": unit,
        "source": source,
        "provider": provider,
        "model": model,
        "available": _is_available(value) if available is None else available,
    }
    if labels:
        record["labels"] = dict(labels)
    if missing_reason:
        record["missing_reason"] = missing_reason
    return record


def percentile(values: list[float], quantile: float) -> float | None:
    """Return a deterministic nearest-rank percentile for a non-empty sample."""

    if not values:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize_values(values: Iterable[float]) -> dict[str, float | int | None]:
    """Summarize seconds or counts with the baseline report percentiles."""

    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "p50": None,
            "p90": None,
            "p95": None,
        }
    return {
        "count": len(clean),
        "min": min(clean),
        "max": max(clean),
        "mean": sum(clean) / len(clean),
        "p50": percentile(clean, 0.50),
        "p90": percentile(clean, 0.90),
        "p95": percentile(clean, 0.95),
    }


def aggregate_metric_records(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    """Aggregate available numeric metric values by metric name.

    Missing, unavailable, and non-numeric records are intentionally excluded;
    their absence is not converted into a fabricated zero.
    """

    values: defaultdict[str, list[float]] = defaultdict(list)
    for record in records:
        if record.get("record_type", "metric") != "metric":
            continue
        if record.get("available") is False:
            continue
        value = record.get("value", _MISSING)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(float(value)) and float(value) >= 0:
            values[str(record.get("metric", "unknown"))].append(float(value))
    return {
        metric: summarize_values(metric_values)
        for metric, metric_values in values.items()
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read local records for offline baseline analysis."""

    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _append_json_line(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
        output.write("\n")


class LatencyRecorder:
    """Non-blocking event-loop recorder backed by a local JSONL writer."""

    def __init__(
        self,
        session_id: str,
        *,
        session_labels: Mapping[str, Any] | None = None,
        path: Path | None = None,
        max_queue_size: int = 1024,
    ) -> None:
        self.session_id = session_id
        self.session_labels = dict(session_labels or {})
        self.path = path or default_metrics_path()
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._writer_task: asyncio.Task[None] | None = None
        self._closed = False
        self._tool_started: dict[str, list[tuple[float, str | None]]] = {}
        self._language_by_turn: dict[str, str] = {}
        self._effective_language_by_turn: dict[str, str] = {}
        self._current_language: str | None = None
        self._current_effective_language: str | None = None
        self.dropped_records = 0

    async def start(self) -> None:
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(
                self._writer(), name="latency-jsonl-writer"
            )

    async def flush(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.flush()
        if self._writer_task is not None:
            await self._queue.put(None)
            await self._writer_task
            self._writer_task = None

    def record_metric(self, **kwargs: Any) -> None:
        if self._closed:
            return
        labels = dict(self.session_labels)
        labels.update(kwargs.pop("labels", {}) or {})
        if labels:
            kwargs["labels"] = labels
        record = make_metric_record(session_id=self.session_id, **kwargs)
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped_records += 1
            logger.warning("latency metrics queue is full; dropping a record")

    def record_missing(
        self,
        *,
        stage: str,
        metric: str,
        unit: str,
        source: str,
        missing_reason: str,
        turn_id: str | None = None,
        speech_id: str | None = None,
        labels: Mapping[str, Any] | None = None,
    ) -> None:
        self.record_metric(
            stage=stage,
            metric=metric,
            value=None,
            unit=unit,
            source=source,
            turn_id=turn_id,
            speech_id=speech_id,
            labels=labels,
            available=False,
            missing_reason=missing_reason,
        )

    def set_effective_voice_language(
        self, language: str, *, turn_id: str | None = None
    ) -> None:
        """Track the successful voice route separately from detected STT language."""

        self._current_effective_language = language
        if isinstance(turn_id, str) and turn_id:
            self._effective_language_by_turn[turn_id] = language

    def record_component_metrics(self, stage: str, metrics: Any) -> None:
        """Record the supported metrics emitted by an STT/LLM/TTS/VAD/EOT object."""

        metric_type = getattr(metrics, "type", type(metrics).__name__.lower())
        metadata = getattr(metrics, "metadata", None)
        provider = getattr(metadata, "model_provider", None)
        model = getattr(metadata, "model_name", None)
        speech_id = getattr(metrics, "speech_id", None)
        request_id = getattr(metrics, "request_id", None)

        fields: dict[str, dict[str, tuple[str, str]]] = {
            "stt_metrics": {
                "duration": ("stt_request_duration", "seconds"),
                "audio_duration": ("stt_audio_duration", "seconds"),
                "acquire_time": ("stt_acquire_time", "seconds"),
            },
            "llm_metrics": {
                "duration": ("llm_generation_duration", "seconds"),
                "ttft": ("llm_ttft", "seconds"),
                "completion_tokens": ("llm_completion_tokens", "tokens"),
                "prompt_tokens": ("llm_prompt_tokens", "tokens"),
                "total_tokens": ("llm_total_tokens", "tokens"),
            },
            "tts_metrics": {
                "ttfb": ("tts_ttfb", "seconds"),
                "duration": ("tts_generation_duration", "seconds"),
                "audio_duration": ("tts_audio_duration", "seconds"),
                "input_tokens": ("tts_input_tokens", "tokens"),
                "output_tokens": ("tts_output_tokens", "tokens"),
            },
            "vad_metrics": {
                "idle_time": ("vad_idle_time", "seconds"),
                "inference_duration_total": ("vad_inference_duration_total", "seconds"),
                "inference_count": ("vad_inference_count", "count"),
            },
            "eot_inference_metrics": {
                "total_duration": ("eot_inference_duration", "seconds"),
                "prediction_duration": ("eot_prediction_duration", "seconds"),
                "detection_delay": ("eot_detection_delay", "seconds"),
                "num_requests": ("eot_request_count", "count"),
            },
            "eou_metrics": {
                "end_of_utterance_delay": ("eou_delay", "seconds"),
                "transcription_delay": ("transcription_delay", "seconds"),
                "on_user_turn_completed_delay": (
                    "on_user_turn_completed_delay",
                    "seconds",
                ),
            },
        }.get(metric_type, {})

        for field_name, (metric_name, unit) in fields.items():
            value = getattr(metrics, field_name, None)
            labels: dict[str, Any] = {}
            if self._current_language:
                labels["language_code"] = self._current_language
            if self._current_effective_language:
                labels["detected_language"] = self._current_language
                labels["effective_voice_language"] = self._current_effective_language
            if _is_available(value):
                self.record_metric(
                    stage=stage,
                    metric=metric_name,
                    value=value,
                    unit=unit,
                    source=f"{stage}.metrics_collected",
                    speech_id=speech_id,
                    request_id=request_id,
                    provider=provider,
                    model=model,
                    labels=labels,
                )
            else:
                self.record_missing(
                    stage=stage,
                    metric=metric_name,
                    unit=unit,
                    source=f"{stage}.metrics_collected",
                    missing_reason="provider reported the metric as unavailable",
                    speech_id=speech_id,
                    labels=labels,
                )

    def record_conversation_item(self, event: Any) -> None:
        item = getattr(event, "item", None)
        if not isinstance(item, ChatMessage):
            return

        role_value = getattr(item, "role", None)
        role = getattr(role_value, "value", role_value)
        if not isinstance(role, str):
            return
        role = role.removeprefix("ChatRole.").casefold()

        turn_id = getattr(item, "id", None)
        if not isinstance(turn_id, str) or not turn_id:
            turn_id = None

        raw_metrics = getattr(item, "metrics", None)
        metrics: Mapping[str, Any] = (
            raw_metrics if isinstance(raw_metrics, Mapping) else {}
        )

        fields: dict[str, tuple[str, str]] = {
            "started_speaking_at": ("started_speaking_at", "unix_seconds"),
            "stopped_speaking_at": ("stopped_speaking_at", "unix_seconds"),
        }
        if role == "user":
            fields.update(
                {
                    "transcription_delay": ("transcription_delay", "seconds"),
                    "end_of_turn_delay": ("eou_delay", "seconds"),
                    "on_user_turn_completed_delay": (
                        "on_user_turn_completed_delay",
                        "seconds",
                    ),
                }
            )
            stage = "user_turn"
        elif role == "assistant":
            fields.update(
                {
                    "e2e_latency": ("e2e_latency", "seconds"),
                    "llm_node_ttft": ("llm_node_ttft", "seconds"),
                    "llm_node_ttfs": ("llm_node_ttfs", "seconds"),
                    "llm_node_tps": ("llm_node_tps", "tokens_per_second"),
                    "tts_node_ttfb": ("tts_node_ttfb", "seconds"),
                    "playback_latency": (
                        "agent_playback_latency",
                        "seconds",
                    ),
                    "provider_request_ids": (
                        "provider_request_ids",
                        "list",
                    ),
                }
            )
            stage = "agent_turn"
        else:
            return

        for field_name, (metric_name, unit) in fields.items():
            value = _turn_metric_value(metrics, field_name)
            labels = {"role": role}
            language = self._language_by_turn.get(turn_id) or self._current_language
            if language:
                labels["language_code"] = language
            effective_language = (
                self._effective_language_by_turn.get(turn_id)
                or self._current_effective_language
            )
            if effective_language:
                labels["detected_language"] = language
                labels["effective_voice_language"] = effective_language
            if value is not None:
                self.record_metric(
                    stage=stage,
                    metric=metric_name,
                    value=value,
                    unit=unit,
                    source="conversation_item.metrics",
                    turn_id=turn_id,
                    labels=labels,
                )
            else:
                self.record_missing(
                    stage=stage,
                    metric=metric_name,
                    unit=unit,
                    source="conversation_item.metrics",
                    missing_reason=(
                        "the turn did not expose this metric or reported an "
                        "unexpected value"
                    ),
                    turn_id=turn_id,
                    labels=labels,
                )

    def record_agent_state(self, event: Any) -> None:
        old_state = getattr(event, "old_state", None)
        new_state = getattr(event, "new_state", None)
        self.record_metric(
            stage="agent_state",
            metric="state_changed",
            value=1,
            unit="event",
            source="session.agent_state_changed",
            labels={"old_state": old_state, "new_state": new_state},
        )
        if new_state == "speaking":
            self.record_metric(
                stage="agent_speech",
                metric="started",
                value=1,
                unit="event",
                source="session.agent_state_changed",
            )
        elif old_state == "speaking":
            self.record_metric(
                stage="agent_speech",
                metric="ended",
                value=1,
                unit="event",
                source="session.agent_state_changed",
            )

    def record_user_state(self, event: Any) -> None:
        old_state = getattr(event, "old_state", None)
        new_state = getattr(event, "new_state", None)
        self.record_metric(
            stage="user_speech",
            metric="state_changed",
            value=1,
            unit="event",
            source="session.user_state_changed",
            labels={"old_state": old_state, "new_state": new_state},
        )
        if new_state == "speaking":
            self.record_metric(
                stage="user_speech",
                metric="detected_started",
                value=1,
                unit="event",
                source="session.user_state_changed",
            )
        elif old_state == "speaking":
            self.record_metric(
                stage="user_speech",
                metric="detected_ended",
                value=1,
                unit="event",
                source="session.user_state_changed",
            )

    def record_transcription(self, event: Any) -> None:
        language = getattr(event, "language", None)
        language_code = getattr(language, "value", language)
        is_final = bool(getattr(event, "is_final", False))
        if is_final and isinstance(language_code, str) and language_code:
            language_code = language_code.casefold()
            self._current_language = language_code
            turn_id = getattr(event, "item_id", None)
            if isinstance(turn_id, str) and turn_id:
                self._language_by_turn[turn_id] = language_code

        if not is_final:
            return
        self.record_metric(
            stage="stt",
            metric="final_transcript_received",
            value=1,
            unit="event",
            source="session.user_input_transcribed",
            turn_id=getattr(event, "item_id", None),
            labels={
                "language": language_code,
                "language_code": language_code,
            },
        )

    def record_speech_created(self, event: Any) -> None:
        handle = getattr(event, "speech_handle", None)
        speech_id = getattr(handle, "id", None)
        self.record_metric(
            stage="agent_speech",
            metric="created",
            value=1,
            unit="event",
            source="session.speech_created",
            speech_id=speech_id,
            labels={"source": getattr(event, "source", None)},
        )

    def record_tool_update(self, event: Any) -> None:
        update = getattr(event, "update", None)
        update_type = getattr(update, "type", None)
        if isinstance(update, ToolCallStarted) or update_type == "tool_call_started":
            function_call = getattr(update, "function_call", None)
            # ToolCallStarted stores call_id on its nested FunctionCall. Keep the
            # direct lookup as a compatibility fallback for older test doubles.
            call_id = getattr(function_call, "call_id", None) or getattr(
                update, "call_id", None
            )
            tool_name = getattr(function_call, "name", None)
            if not call_id:
                self.record_metric(
                    stage="tool",
                    metric="tool_execution_requested",
                    value=1,
                    unit="event",
                    source="session.tool_execution_updated",
                    labels={"tool_name": tool_name, "correlation": "missing_call_id"},
                )
                return
            self._tool_started.setdefault(call_id, []).append(
                (time.monotonic(), tool_name)
            )
            self.record_metric(
                stage="tool",
                metric="tool_execution_requested",
                value=1,
                unit="event",
                source="session.tool_execution_updated",
                request_id=call_id,
                labels={"tool_name": tool_name},
            )
            return
        if isinstance(update, ToolCallEnded) or update_type == "tool_call_ended":
            call_id = getattr(update, "call_id", None)
            if not call_id:
                self.record_metric(
                    stage="tool",
                    metric="tool_execution_completed",
                    value=1,
                    unit="event",
                    source="session.tool_execution_updated",
                    labels={"correlation": "missing_call_id"},
                )
                return
            starts = self._tool_started.get(call_id)
            if not starts:
                self.record_metric(
                    stage="tool",
                    metric="tool_execution_completed",
                    value=1,
                    unit="event",
                    source="session.tool_execution_updated",
                    request_id=call_id,
                    labels={"correlation": "missing_start", "status": "unmatched"},
                )
                return
            started_at, tool_name = starts.pop(0)
            if not starts:
                self._tool_started.pop(call_id, None)
            status = getattr(update, "status", None)
            self.record_metric(
                stage="tool",
                metric="tool_duration",
                value=max(0.0, time.monotonic() - started_at),
                unit="seconds",
                source="session.tool_execution_updated",
                request_id=call_id,
                speech_id=getattr(update, "speech_id", None),
                labels={"tool_name": tool_name, "status": status},
            )
            self.record_metric(
                stage="tool",
                metric="tool_execution_completed",
                value=1,
                unit="event",
                source="session.tool_execution_updated",
                request_id=call_id,
                labels={"tool_name": tool_name, "status": status},
            )
            return
        if (
            isinstance(update, ToolReplyUpdated) or update_type == "tool_reply_updated"
        ) and getattr(update, "status", None) == "scheduled":
            self.record_metric(
                stage="tool",
                metric="llm_followup_started",
                value=1,
                unit="event",
                source="session.tool_execution_updated",
                speech_id=getattr(update, "speech_id", None),
                labels={"status": "scheduled"},
            )

    def record_tools_executed(self, event: Any) -> None:
        calls = getattr(event, "function_calls", [])
        self.record_metric(
            stage="tool",
            metric="tool_call_count",
            value=len(calls),
            unit="count",
            source="session.function_tools_executed",
        )
        for function_call in calls:
            self.record_metric(
                stage="tool",
                metric="llm_followup_started",
                value=1,
                unit="event",
                source="session.function_tools_executed",
                request_id=getattr(function_call, "call_id", None),
                labels={"tool_name": getattr(function_call, "name", None)},
            )

    def record_session_summary(self, report: Mapping[str, Any]) -> None:
        safe_fields = {
            key: report.get(key)
            for key in (
                "job_id",
                "room_id",
                "room",
                "duration_ms",
                "user_turns",
                "errors",
                "close_reason",
                "sdk_version",
                "agent_name",
                "usage",
            )
        }
        record = {
            "schema_version": 1,
            "record_type": "session_summary",
            "session_id": self.session_id,
            "timestamp": _timestamp(),
            "monotonic_seconds": time.monotonic(),
            "clock_domain": "backend_process",
            "source": "job_context.session_report",
            "report": safe_fields,
        }
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped_records += 1
            logger.warning("latency metrics queue is full; dropping session summary")

    async def _writer(self) -> None:
        while True:
            record = await self._queue.get()
            try:
                if record is None:
                    return
                await asyncio.to_thread(_append_json_line, self.path, record)
            except Exception:
                logger.exception("failed to write latency metric")
            finally:
                self._queue.task_done()


def attach_session_listeners(
    session: Any,
    recorder: LatencyRecorder,
    *,
    turn_detector: Any | None = None,
) -> None:
    """Attach only public AgentSession/component metric and event listeners."""

    session.on("conversation_item_added", recorder.record_conversation_item)
    session.on("agent_state_changed", recorder.record_agent_state)
    session.on("user_state_changed", recorder.record_user_state)
    session.on("user_input_transcribed", recorder.record_transcription)
    session.on("speech_created", recorder.record_speech_created)
    session.on("tool_execution_updated", recorder.record_tool_update)
    session.on("function_tools_executed", recorder.record_tools_executed)

    components = (
        ("stt", getattr(session, "stt", None)),
        ("llm", getattr(session, "llm", None)),
        ("tts", getattr(session, "tts", None)),
        ("vad", getattr(session, "vad", None)),
        ("eot", turn_detector),
    )
    for stage, component in components:
        if component is not None and hasattr(component, "on"):
            component.on(
                "metrics_collected",
                lambda metrics, stage=stage: recorder.record_component_metrics(
                    stage, metrics
                ),
            )
