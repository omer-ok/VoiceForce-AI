from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ChatMessage

from voiceforce_agent.latency_metrics import (
    LatencyRecorder,
    aggregate_metric_records,
    make_metric_record,
    percentile,
    summarize_values,
)


def test_metric_record_has_explicit_source_units_and_clock_domain() -> None:
    record = make_metric_record(
        session_id="room-1",
        turn_id="turn-1",
        speech_id="speech-1",
        stage="llm",
        metric="llm_ttft",
        value=0.42,
        unit="seconds",
        source="llm.metrics_collected",
    )

    assert record["value"] == 0.42
    assert record["unit"] == "seconds"
    assert record["source"] == "llm.metrics_collected"
    assert record["speech_id"] == "speech-1"
    assert record["clock_domain"] == "backend_process"


def test_percentiles_and_empty_aggregation_are_deterministic() -> None:
    assert percentile([3.0, 1.0, 2.0, 4.0], 0.5) == 2.0
    assert summarize_values([])["count"] == 0
    assert (
        aggregate_metric_records(
            [
                {"record_type": "metric", "metric": "ttft", "value": 1.0},
                {
                    "record_type": "metric",
                    "metric": "ttft",
                    "value": None,
                    "available": False,
                },
                {"record_type": "metric", "metric": "ttft", "value": "unknown"},
                {"record_type": "session_summary", "report": {}},
            ]
        )["ttft"]["count"]
        == 1
    )


@pytest.mark.asyncio
async def test_recorder_writes_jsonl_without_blocking_the_callback(
    tmp_path: Path,
) -> None:
    output = tmp_path / "latency.jsonl"
    recorder = LatencyRecorder("room-1", path=output)
    await recorder.start()
    recorder.record_metric(
        stage="stt",
        metric="transcription_delay",
        value=0.3,
        unit="seconds",
        source="conversation_item.metrics",
    )
    await recorder.close()

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert records[0]["session_id"] == "room-1"
    assert records[0]["metric"] == "transcription_delay"


def test_recorder_adds_stable_session_labels_without_changing_session_id() -> None:
    recorder = LatencyRecorder("job-1", session_labels={"room_name": "console"})
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]

    recorder.record_metric(
        stage="session",
        metric="connected",
        value=1,
        unit="event",
        source="session.connected",
    )

    assert captured[0]["session_id"] == "job-1"
    assert captured[0]["labels"] == {"room_name": "console"}


def test_component_metrics_keep_speech_id_and_record_unavailable_values() -> None:
    recorder = LatencyRecorder("room-1")
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]
    recorder._current_language = "ur"

    metrics = SimpleNamespace(
        type="llm_metrics",
        duration=1.2,
        ttft=0.4,
        completion_tokens=10,
        prompt_tokens=20,
        total_tokens=30,
        speech_id="speech-7",
        request_id="request-7",
        metadata=SimpleNamespace(model_provider="openai", model_name="gpt-5-mini"),
    )
    recorder.record_component_metrics("llm", metrics)

    assert captured
    assert all(record["speech_id"] == "speech-7" for record in captured)
    assert any(record["metric"] == "llm_ttft" for record in captured)
    assert all(record["labels"] == {"language_code": "ur"} for record in captured)


def _capture_conversation_records(message: ChatMessage) -> list[dict]:
    recorder = LatencyRecorder("room-1")
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]
    recorder.record_conversation_item(SimpleNamespace(item=message))
    return captured


def _records_by_metric(records: list[dict]) -> dict[str, dict]:
    return {record["metric"]: record for record in records}


def test_user_turn_metrics_read_dictionary_backed_metrics_report() -> None:
    message = ChatMessage(role="user", content=[], id="user-turn-1")
    message.metrics = {
        "started_speaking_at": 100.0,
        "stopped_speaking_at": 101.0,
        "transcription_delay": 0.2,
        "end_of_turn_delay": 0.3,
        "on_user_turn_completed_delay": 0.04,
    }

    records = _records_by_metric(_capture_conversation_records(message))

    assert records["transcription_delay"]["value"] == 0.2
    assert records["eou_delay"]["value"] == 0.3
    assert records["on_user_turn_completed_delay"]["value"] == 0.04
    assert records["started_speaking_at"]["value"] == 100.0
    assert records["stopped_speaking_at"]["value"] == 101.0
    assert all(record["available"] for record in records.values())
    assert all(record["turn_id"] == "user-turn-1" for record in records.values())
    assert all(record["labels"] == {"role": "user"} for record in records.values())


def test_assistant_turn_metrics_capture_latency_rates_and_provider_ids() -> None:
    message = ChatMessage(role="assistant", content=[], id="assistant-turn-1")
    message.metrics = {
        "started_speaking_at": 200.0,
        "stopped_speaking_at": 201.0,
        "e2e_latency": 0.8,
        "llm_node_ttft": 0.2,
        "llm_node_ttfs": 0.25,
        "llm_node_tps": 42.0,
        "tts_node_ttfb": 0.3,
        "playback_latency": 0.05,
        "provider_request_ids": ["llm-request-1", "tts-request-1"],
    }

    records = _records_by_metric(_capture_conversation_records(message))

    assert records["e2e_latency"]["value"] == 0.8
    assert records["llm_node_ttft"]["value"] == 0.2
    assert records["llm_node_ttfs"]["value"] == 0.25
    assert records["llm_node_tps"]["value"] == 42.0
    assert records["llm_node_tps"]["unit"] == "tokens_per_second"
    assert records["tts_node_ttfb"]["value"] == 0.3
    assert records["agent_playback_latency"]["value"] == 0.05
    assert records["provider_request_ids"]["value"] == [
        "llm-request-1",
        "tts-request-1",
    ]
    assert all(record["available"] for record in records.values())
    assert all(record["turn_id"] == "assistant-turn-1" for record in records.values())
    assert all(record["labels"] == {"role": "assistant"} for record in records.values())


@pytest.mark.parametrize("metrics", [{}, None])
def test_empty_or_null_turn_metrics_are_recorded_as_missing(
    metrics: dict | None,
) -> None:
    message = ChatMessage(role="assistant", content=[], id="assistant-turn-2")
    message.metrics = metrics

    records = _capture_conversation_records(message)

    assert len(records) == 9
    assert all(record["available"] is False for record in records)
    assert all(record["value"] is None for record in records)
    assert all(record["turn_id"] == "assistant-turn-2" for record in records)
    assert all(record["labels"] == {"role": "assistant"} for record in records)


def test_zero_valued_turn_metrics_remain_valid_measurements() -> None:
    message = ChatMessage(role="assistant", content=[], id="assistant-turn-3")
    message.metrics = {
        "started_speaking_at": 0.0,
        "stopped_speaking_at": 0.0,
        "e2e_latency": 0.0,
        "llm_node_ttft": 0.0,
        "llm_node_ttfs": 0.0,
        "llm_node_tps": 0.0,
        "tts_node_ttfb": 0.0,
        "playback_latency": 0.0,
        "provider_request_ids": [],
    }

    records = _capture_conversation_records(message)

    assert all(record["available"] for record in records)
    assert all(record["value"] == 0 or record["value"] == [] for record in records)


def test_unexpected_turn_metric_values_are_missing_not_measurements() -> None:
    message = ChatMessage(role="assistant", content=[], id="assistant-turn-4")
    message.metrics = {
        "e2e_latency": "not-a-duration",
        "llm_node_ttft": 0.2,
        "llm_node_tps": -1.0,
        "provider_request_ids": ["valid-id", 7],
    }

    records = _records_by_metric(_capture_conversation_records(message))

    assert records["llm_node_ttft"]["available"] is True
    assert records["llm_node_ttft"]["value"] == 0.2
    for metric in ("e2e_latency", "llm_node_tps", "provider_request_ids"):
        assert records[metric]["available"] is False
        assert records[metric]["value"] is None


def test_turn_role_and_missing_turn_id_do_not_create_false_correlations() -> None:
    user_message = ChatMessage(role="user", content=[], id="user-turn-5")
    user_message.metrics = {"transcription_delay": 0.1}
    assistant_message = ChatMessage(role="assistant", content=[])
    object.__setattr__(assistant_message, "id", None)
    assistant_message.metrics = {"e2e_latency": 0.4}
    developer_message = ChatMessage(role="developer", content=[], id="not-a-turn")
    developer_message.metrics = {"e2e_latency": 0.5}

    records = (
        _capture_conversation_records(user_message)
        + _capture_conversation_records(assistant_message)
        + _capture_conversation_records(developer_message)
    )

    assert any(
        record["metric"] == "transcription_delay"
        and record["labels"] == {"role": "user"}
        and record["turn_id"] == "user-turn-5"
        for record in records
    )
    assistant_records = [
        record for record in records if record["labels"] == {"role": "assistant"}
    ]
    assert assistant_records
    assert all(record["turn_id"] is None for record in assistant_records)
    assert not any(record["labels"] == {"role": "developer"} for record in records)


def test_conversation_metrics_and_tool_duration_are_correlated() -> None:
    recorder = LatencyRecorder("room-1")
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]

    message = ChatMessage(role="assistant", content=["response"], id="turn-4")
    message.metrics = {
        "llm_node_ttft": 0.2,
        "tts_node_ttfb": 0.3,
        "playback_latency": 0.1,
        "e2e_latency": 0.6,
    }
    recorder.record_conversation_item(SimpleNamespace(item=message))
    recorder.record_tool_update(
        SimpleNamespace(
            update=SimpleNamespace(
                type="tool_call_started",
                call_id="call-1",
                function_call=SimpleNamespace(name="search_demo_properties"),
            )
        )
    )
    recorder.record_tool_update(
        SimpleNamespace(
            update=SimpleNamespace(
                type="tool_call_ended",
                call_id="call-1",
                status="done",
            )
        )
    )

    assert any(record["turn_id"] == "turn-4" for record in captured)
    tool_records = [
        record for record in captured if record["metric"] == "tool_duration"
    ]
    assert len(tool_records) == 1
    assert tool_records[0]["turn_id"] is None
    assert tool_records[0]["value"] >= 0


def test_tool_lifecycle_uses_nested_call_id_and_handles_repeated_calls() -> None:
    recorder = LatencyRecorder("room-1")
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]

    def started(call_id: str) -> None:
        recorder.record_tool_update(
            SimpleNamespace(
                update=SimpleNamespace(
                    type="tool_call_started",
                    function_call=SimpleNamespace(
                        call_id=call_id, name="search_demo_properties"
                    ),
                )
            )
        )

    def ended(call_id: str) -> None:
        recorder.record_tool_update(
            SimpleNamespace(
                update=SimpleNamespace(
                    type="tool_call_ended", call_id=call_id, status="done"
                )
            )
        )

    started("call-1")
    started("call-2")
    started("call-1")
    ended("call-2")
    ended("call-1")
    ended("call-1")

    durations = [record for record in captured if record["metric"] == "tool_duration"]
    assert len(durations) == 3
    assert {record["request_id"] for record in durations} == {
        "call-1",
        "call-2",
    }
    assert all(record["turn_id"] is None for record in durations)


def test_tool_lifecycle_records_missing_correlation_without_using_none_as_a_key() -> (
    None
):
    recorder = LatencyRecorder("room-1")
    captured: list[dict] = []
    recorder._queue.put_nowait = captured.append  # type: ignore[method-assign]

    recorder.record_tool_update(
        SimpleNamespace(
            update=SimpleNamespace(
                type="tool_call_started",
                function_call=SimpleNamespace(name="search_demo_properties"),
            )
        )
    )
    recorder.record_tool_update(
        SimpleNamespace(update=SimpleNamespace(type="tool_call_ended", status="error"))
    )

    assert any(
        record["labels"]["correlation"] == "missing_call_id" for record in captured
    )
    assert not any(record["metric"] == "tool_duration" for record in captured)
