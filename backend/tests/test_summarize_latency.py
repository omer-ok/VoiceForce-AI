from __future__ import annotations

from pathlib import Path

from scripts.summarize_latency import (
    build_report,
    build_turn_diagnostics,
    filter_records,
)


def test_filter_keeps_one_session_and_room_correlation_only() -> None:
    records = [
        {
            "record_type": "metric",
            "session_id": "job-1",
            "labels": {"room_name": "console"},
            "metric": "e2e_latency",
            "value": 1.0,
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-2",
            "labels": {"room_name": "console"},
            "metric": "e2e_latency",
            "value": 2.0,
            "available": True,
        },
    ]

    filtered = filter_records(records, session_ids={"job-1"})

    assert len(filtered) == 1
    assert filtered[0]["value"] == 1.0


def test_diagnostics_follow_explicit_sdk_links_only_within_session_and_clock() -> None:
    def record(session, **fields):
        return {
            "session_id": session,
            "clock_domain": "backend_process",
            "available": True,
            **fields,
        }

    records = [
        record(
            "one", stage="agent_turn", turn_id="reply", metric="e2e_latency", value=4.1
        ),
        record(
            "one",
            stage="correlation",
            turn_id="reply",
            speech_id="speech",
            metric="speech_item_link",
            value=1,
        ),
        record(
            "one",
            stage="correlation",
            speech_id="speech",
            request_id="call",
            metric="speech_tool_link",
            value=1,
        ),
        record(
            "one", stage="tool", request_id="call", metric="tool_duration", value=0.02
        ),
        record("two", stage="tool", request_id="call", metric="tool_duration", value=8),
        {
            "session_id": "one",
            "clock_domain": "browser_performance",
            "turn_id": "reply",
            "metric": "e2e_latency",
            "value": 9,
            "available": True,
        },
    ]
    diagnostics = build_turn_diagnostics(records)
    linked = next(item for item in diagnostics if item["speech_id"] == "speech")
    assert linked["metrics"]["e2e_latency"] == 4.1
    assert linked["metrics"]["tool_execution_duration"] == 0.02
    assert not linked["browser_timeline"]
    assert len(diagnostics) == 3


def test_fast_reply_link_preserves_individual_response_metrics() -> None:
    common = {"session_id": "one", "clock_domain": "backend_process", "available": True}
    records = [
        {
            **common,
            "stage": "tool",
            "speech_id": "parent",
            "request_id": "call",
            "metric": "fast_property_reply_scheduled",
            "value": 1,
            "labels": {"reply_speech_id": "child"},
        },
        {
            **common,
            "stage": "tool",
            "request_id": "call",
            "metric": "tool_duration",
            "value": 0.02,
        },
        {
            **common,
            "stage": "correlation",
            "speech_id": "child",
            "turn_id": "reply",
            "metric": "speech_item_link",
            "value": 1,
        },
        {
            **common,
            "stage": "correlation",
            "speech_id": "parent",
            "turn_id": "other",
            "metric": "speech_item_link",
            "value": 1,
        },
        {
            **common,
            "stage": "agent_turn",
            "turn_id": "reply",
            "metric": "e2e_latency",
            "value": 4.0,
        },
        {
            **common,
            "stage": "agent_turn",
            "turn_id": "other",
            "metric": "e2e_latency",
            "value": 1.0,
        },
    ]

    diagnostics = build_turn_diagnostics(records)
    assert len(diagnostics) == 2
    reply = next(item for item in diagnostics if item["turn_id"] == "reply")
    other = next(item for item in diagnostics if item["turn_id"] == "other")
    assert reply["speech_id"] == "child"
    assert reply["metrics"]["e2e_latency"] == 4.0
    assert reply["metrics"]["tool_execution_duration"] == 0.02
    assert other["metrics"]["e2e_latency"] == 1.0
    filtered = filter_records(records, session_ids={"one"}, turn_ids={"reply"})
    assert any(item.get("metric") == "tool_duration" for item in filtered)
    assert (
        build_turn_diagnostics(filtered)[0]["metrics"]["tool_execution_duration"]
        == 0.02
    )


def test_report_separates_component_and_turn_metrics_and_preserves_missing() -> None:
    records = [
        {
            "record_type": "metric",
            "session_id": "job-1",
            "turn_id": "turn-1",
            "speech_id": "speech-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 2.0,
            "source": "conversation_item.metrics",
            "stage": "agent_turn",
            "metric": "e2e_latency",
            "value": 1.0,
            "unit": "seconds",
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-1",
            "speech_id": "speech-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 1.0,
            "source": "llm.metrics_collected",
            "stage": "llm",
            "metric": "llm_ttft",
            "value": 0.4,
            "unit": "seconds",
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-1",
            "turn_id": "turn-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 3.0,
            "source": "conversation_item.metrics",
            "stage": "agent_turn",
            "metric": "tts_node_ttfb",
            "value": None,
            "unit": "seconds",
            "available": False,
            "missing_reason": "not exposed",
        },
    ]

    report = build_report(
        records,
        files=[Path("backend/data/latency_metrics.jsonl")],
        filters={"session_id": ["job-1"]},
        include_diagnostics=True,
    )

    assert report["session_ids"] == ["job-1"]
    assert report["metrics_by_scope"]["per_turn"]["e2e_latency"]["count"] == 1
    assert report["metrics_by_scope"]["per_component"]["llm_ttft"]["count"] == 1
    assert report["observation_counts"]["tts_node_ttfb"] == {
        "available": 0,
        "missing": 1,
        "total": 1,
    }
    diagnostic = next(
        item for item in report["turn_diagnostics"] if item["turn_id"] == "turn-1"
    )
    assert diagnostic["metrics"]["e2e_latency"] == 1.0
    assert diagnostic["metrics"]["tts_node_ttfb"] is None
    assert "llm_request_start" in diagnostic["missing_stages"]
